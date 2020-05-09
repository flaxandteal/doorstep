"""Engine for running a job on a Pachyderm cluster."""

from contextlib import contextmanager
import asyncio
import time
import os
import sys
import json
import uuid
import pypachy
import jinja2
import logging
from concurrent.futures import ThreadPoolExecutor
from .pachyderm_proxy.repo import make_repo
from .pachyderm_proxy.pipeline import make_pipeline
from .pachyderm_proxy.job_error import JobFailedException
from .pachyderm_proxy.pypachy_wrapper import PfsClientWrapper
from .engine import Engine

ALLOWED_IMAGES = [
    ('lintol/doorstep', 'latest'),
    ('lintol/ds-csvlint', 'latest')
]


class PachydermEngine(Engine):
    """Allow execution of workflows on a Pachyderm cluster."""

    _retry_count = 120
    _retry_delay = 1.0
    _retry_processing_count = 50
    pipeline_definition = None

    def __init__(self, config=None):
        self.logger = logging.getLogger(__name__)
        self.logger.debug("Setting up Pachyderm engine")

        self.set_clients(
            pps=pypachy.pps_client.PpsClient(),
            pfs=PfsClientWrapper()
        )

        self._pipeline_template = os.path.join(
            os.path.dirname(__file__),
            'pachyderm_proxy',
            'doorstep.json'
        )

    def get_definition(self, data_name='data', processors_name='processors'):
        """Load and set the pipeline definition."""

        if not self.pipeline_definition:
            with open(self._pipeline_template, 'r') as file_obj:
                template = jinja2.Template(file_obj.read())
            self.pipeline_definition = json.loads(template.render(
                data=data_name,
                processors=processors_name,
                valid_images=['%s:%s' % pair for pair in ALLOWED_IMAGES]
            ))

        return self.pipeline_definition

    def get_clients(self):
        """Get the client objects used to communicate with Pachyderm."""

        return (self._clients['pps'], self._clients['pfs'])

    def set_clients(self, pps, pfs):
        """Set the client objects to communicate with Pachyderm."""

        self._clients = {
            'pps': pps,
            'pfs': pfs
        }

    def add_processor(self, modules, context, session):
        """Mark a module_name as a processor."""

        self.logger.debug("Adding processor")
        self.logger.debug(context)

        lang = 'C.UTF-8' # TODO: more sensible default

        if 'lang' in context:
            # TODO: check lang is valid
            lang = context['lang']

        if 'definitions' not in context:
            context['definitions'] = {str(uuid.uuid4()): {}}

        for uid, processor in context['definitions'].items():
            docker_image = 'lintol/doorstep'
            docker_revision = 'latest'

            if (docker_image, docker_revision) not in ALLOWED_IMAGES:
                raise RuntimeError(_("Docker image supplied is not whitelisted"))

            if 'docker' in processor:
                if 'image' in processor['docker']:
                    docker_image = processor['docker']['image']
                    docker_revision = processor['docker']['revision']

            docker = '{image}:{revision}'.format(image=docker_image, revision=docker_revision)
            configuration = {
                'definition': processor,
                'settings': context['settings'] if 'settings' in context else {}
            }

            context_json = json.dumps(configuration).encode('utf-8')

            files = {
                'context.json': context_json,
                'LANG': lang.encode('utf-8'),
                'IMAGE': docker.encode('utf-8')
            }

            if 'module' in processor:
                filename = processor['module']
                if processor['module'] in modules:
                    content = modules[processor['module']]
                else:
                    raise RuntimeError(_("Module content missing from processor %s") % processor['module'])
                files[filename] = content

            files = {os.path.join('/', uid, k): v for k, v in files.items()}

            self._add_files('processors', files, session)

        self.logger.debug("Added processor")

    def add_data(self, filename, content, redirect, session, bucket=None):
        """Prepare to send a data file to Pachyderm."""

        self.logger.debug("Adding data")

        filename = '/%s' % filename

        self._add_files('data', {filename: content}, session, bucket)

        self.logger.debug("Added data")

    def _add_files(self, category, files, session, bucket=None):
        """Transfer file to Pachyderm."""

        with session[category].make_commit('master') as commit:
            for filename, content in files.items():
                if bucket:
                    commit.put_file_url(
                        filename,
                        's3://%s/%s' % (bucket, content)
                    )
                else:
                    commit.put_file_bytes(
                        filename,
                        content
                    )

    @contextmanager
    def make_session(self):
        """Set up a workflow session.

        This creates a self-contained set of Pachyderm constructs representing our operation.
        """

        clients = self._clients

        name = 'doorstep-%s' % str(uuid.uuid4())
        data_name = '%s-data' % name
        processors_name = '%s-processors' % name

        pipeline_definition = self.get_definition(
            data_name=data_name,
            processors_name=processors_name
        )

        with make_repo(clients, data_name) as data_repo, \
                make_repo(clients, processors_name) as processors_repo:
            session = {
                'name': name,
                'data': data_repo,
                'processors': processors_repo
            }
            with make_pipeline(clients, pipeline_definition, session) as pipeline:
                session['pipeline'] = pipeline
                yield session

    async def run(self, filename, workflow_module, context, bucket=None):
        """Execute the pipeline on a Pachyderm cluster."""

        with self.make_session() as session:
            with open(workflow_module, 'r') as file_obj:
                self.add_processor({'processor.py', file_obj.read().encode('utf-8')}, context, session)

            if bucket:
                content = filename
            else:
                with open(filename, 'r') as file_obj:
                    content = file_obj.read().encode('utf-8')

            # TODO: safely set file extension
            self.add_data('data.csv', content, False, session, bucket)

            monitor_pipeline, monitor_output = await self.monitor_pipeline(session)

            commit = await monitor_output

            monitor_pipeline.cancel()

            results = await self.get_output(session)

        return results

    @staticmethod
    async def _wait_for_pipeline(pipeline, retry_count, retry_processing_count, retry_delay):
        """Wait until pipeline has completed."""

        async def _tick_callback():
            sys.stdout.write('.')
            sys.stdout.flush()
            await asyncio.sleep(retry_delay)

        # Wait for pipeline run to start
        await pipeline.wait_for_run(
            retry_count,
            tick_callback=_tick_callback,
            error_suffix=" to start"
        )

        # Wait for pipeline run to finish
        return await pipeline.wait_for_run(
            retry_processing_count,
            (pypachy.JOB_STARTING, pypachy.JOB_RUNNING),
            tick_callback=_tick_callback,
            error_suffix=" to finish"
        )

    async def watch_for_output(self, queue, session):
        commit_queue = await session['pipeline'].watch_commits()
        input_repos = {session['data'].get_name(), session['processors'].get_name()}

        provenance = False
        while not input_repos == provenance:
            commit = await commit_queue.get()
            provenance = {p['repo_name'] for p in commit.get_provenance()}

        await queue.put(commit)

        await session['pipeline'].stop_watching_commits()

    async def monitor_pipeline(self, session):
        """Check pipeline for completion and process results."""

        loop = asyncio.get_event_loop()

        # Wait for the output, which Pachyderm lets us subscribe to,
        # and poll the job, in case there isn't any

        queue = asyncio.Queue()
        asyncio.ensure_future(self.watch_for_output(queue, session))
        pipeline_fut = asyncio.ensure_future(self.wait_for_pipeline(session))

        return (pipeline_fut, queue.get())

    async def get_output(self, session):
        output = session['pipeline'].pull_output('/raw/processor.json')

        return '\n'.join([line.decode('utf-8') for line in output])

    def wait_for_commit(self, session):
        for commit in session['pipeline'].subscribe_output_commit():
            print(commit.get_provenance())

    async def wait_for_pipeline(self, session):
        try:
            job = await self._wait_for_pipeline(
                session['pipeline'],
                self._retry_count,
                self._retry_processing_count,
                self._retry_delay
            )
        except JobFailedException as exc:
            logs = exc.logs()
            if logs:
                print(logs[0])
                print('\n'.join([log.message.rstrip() for log in logs]))
            raise exc
