"""Engine for running over a dask cluster."""

import aiodocker
import sys
import traceback
import shutil
import requests
import uuid
import os
import logging
import asyncio
from urllib.parse import urlparse
from contextlib import contextmanager
from ..reports.report import Report, get_report_class_from_preset, combine_reports
from ..file import make_file_manager
import docker
import tempfile
import json
from .engine import Engine
from ..errors import LintolDoorstepException, LintolDoorstepContainerException
from ..context import DoorstepContext
from ..ini import DoorstepIni


DEFAULT_CLIENT = 'tcp://localhost:8786'

class DockerEngine(Engine):
    """Allow execution on local docker containers."""

    client_url = DEFAULT_CLIENT
    bind_ltldoorstep_module = False

    def __init__(self, config=None):
        if config and 'engine' in config:
            config = config['engine']
            if 'url' in config:
                self.client_url = config['url']
            if 'bind' in config and config['bind']:
                self.bind_ltldoorstep_module = True

    @staticmethod
    def description():
        return _("Run processor(s) locally via Docker")

    @staticmethod
    def config_help():
        return {
            'bind': _("Useful for debugging ltldoorstep itself,\n" +
                "bind-mounts the ltldoorstep module into the executing container")
        }

    def add_data(self, filename, content, redirect, session):
        data = {
            'filename': filename,
            'content': content
        }
        asyncio.ensure_future(session['queue'].put(data))

    def add_processor(self, modules, ini, session):
        """Mark a module_name as a processor."""

        lang = 'C.UTF-8' # TODO: more sensible default

        if type(ini) is dict:
            ini = DoorstepIni.from_dict(ini)

        if ini.lang:
            # TODO: check lang is valid
            lang = ini.lang

        if 'processors' not in session:
            session['processors'] = []

        for uid, context in ini.definitions.items():
            docker_image = 'lintol/doorstep'
            docker_revision = 'latest'

            if context.docker['image']:
                docker_image = context.docker['image']
            if context.docker['revision']:
                docker_image = context.docker['revision']

            docker = '{image}:{revision}'.format(image=docker_image, revision=docker_revision)

            filename = None
            content = None
            if context.module:
                filename = context.module
                if context.module in modules:
                    content = modules[context.module]
                else:
                    error_msg = _("Module content missing from processor %s") % context.module
                    logging.error(error_msg)
                    raise RuntimeError(error_msg)

            session['processors'].append({
                'name' : uid,
                'filename': filename,
                'content': content,
                'context': context
            })

    async def run(self, filename, workflow_module, context, bucket=None):
        """Start the execution process over the cluster."""

        with open(filename, 'r') as data_file:
            data_content = data_file.read()

        basename = os.path.basename(workflow_module)
        with open(workflow_module, 'r') as workflow_file:
            workflow_content = workflow_file.read()

        processors = [{
            'name': 'processor',
            'context': context,
            'filename': basename,
            'content': workflow_content
        }]

        return await self._run(filename, data_content, processors, self.bind_ltldoorstep_module)

    async def monitor_pipeline(self, session):
        session['completion'] = asyncio.Event()

        async def run_when_ready():
            # await session['completion'].acquire()
            data = await session['queue'].get()
            try:
                result = await self._run(data['filename'], data['content'], session['processors'], self.bind_ltldoorstep_module)
                session['result'] = result
            except Exception as error:
                __, __, exc_traceback = sys.exc_info()
                traceback.print_tb(exc_traceback)
                if not isinstance(error, LintolDoorstepException):
                    error = LintolDoorstepException(error)
                session['result'] = error
            finally:
                session['completion'].set()

        asyncio.ensure_future(run_when_ready())

        return (False, session['completion'].wait())

    async def get_output(self, session):
        await session['completion'].wait()

        result = session['result']

        if isinstance(result, LintolDoorstepException):
            raise result

        return result

    @staticmethod
    async def _run(data_filename, data_content, processors, bind_ltldoorstep_module):
        """Start the execution process over the cluster for a given client."""

        result = None

        filename = data_filename
        if type(data_content) == bytes:
            data_content = data_content.decode('utf-8')

        content = {
            filename: data_content
        }
        for processor in processors:
            pc = processor['content']
            if not pc:
                pc = ''
            if processor['filename']:
                if type(pc) == bytes:
                    pc = pc.decode('utf-8')
                content[processor['filename']] = pc

        with tempfile.TemporaryDirectory('-doorstep-docker-engine-storage') as mounted_dir, make_file_manager(content=content) as file_manager:
            data_file = file_manager.get(data_filename)
            out_root = os.path.join(mounted_dir, 'out')
            data_root = os.path.join(mounted_dir, 'data')
            os.makedirs(data_root)
            os.makedirs(os.path.join(out_root, 'raw'))

            report_files = []
            for processor in processors:
                processor_root = os.path.join(mounted_dir, 'processors', processor['name'])
                context = processor['context']

                os.makedirs(processor_root)

                if 'supplementary' in context:
                    supplementary_internal = {}
                    for i, (key, supplementary) in enumerate(context['supplementary'].items()):
                        error = _("(unknown error)")
                        if supplementary.startswith('error://'):
                            error = supplementary[len('error://'):]
                            raise RuntimeError(_("Supplementary data could not be retrieved: %s") % error)

                        supplementary_basename = 's%d-%s' % (i, os.path.basename(urlparse(supplementary).path))

                        r = requests.get(supplementary, stream=True)
                        if r.status_code != 200:
                            raise RuntimeError(_("Could not retrieve supplementary data: %d" % r.status_code))

                        print(_("Downloading %s") % supplementary)
                        with open(os.path.join(processor_root, supplementary_basename), 'wb') as supplementary_file:
                            for chunk in r.iter_content(chunk_size=1024):
                                supplementary_file.write(chunk)

                        supplementary_internal[key] = {
                            'source': supplementary,
                            'location': os.path.join('/pfs', 'processors', processor['name'], supplementary_basename)
                        }

                    context['supplementary'] = supplementary_internal

                with open(os.path.join(processor_root, 'context.json'), 'w') as context_file:
                    json.dump(context, context_file)

                if processor['filename']:
                    shutil.copy(file_manager.get(processor['filename']), os.path.join(processor_root, processor['filename']))
                data_basename = os.path.basename(data_filename)
                shutil.copy(data_file, os.path.join(data_root, data_basename))

                mounts = [('mounted_dir', '/pfs')]

                docker_image = 'lintol/doorstep'
                docker_revision = 'latest'
                lang = 'C.UTF-8' # TODO: more sensible default

                for code, definition in context['definitions'].items():
                    definition = definition['definition']
                    if definition['docker']['image']:
                        docker_image = definition['docker']['image']
                    if definition['docker']['revision']:
                        docker_revision = definition['docker']['revision']

                    if context['lang']:
                        # TODO: check lang is valid
                        lang = context['lang']

                    envs = {
                        'LANG': lang,
                        'LINTOL_PROCESSOR_DIRECTORY': '/pfs/processors/%s' % processor['name'],
                        'LINTOL_OUTPUT_FILE': '/pfs/out/raw/%s.json' % processor['name'],
                        'LINTOL_CONTEXT': '/pfs/processors/%s/context.json' % processor['name'],
                        'LINTOL_INPUT_DATA': '/pfs/data',
                        'LINTOL_DATA_FILE': data_basename
                    }
                    report_files.append(os.path.join(out_root, 'raw', '%s.json' % processor['name']))

                    client = docker.from_env()
                    mounts = [
                        docker.types.Mount('/pfs', mounted_dir, type='bind')
                    ]

                    if bind_ltldoorstep_module:
                        ltldoorstep_root_dir = os.path.join(
                            os.path.dirname(__file__),
                            '..',
                            '..',
                            '..'
                        )
                        mounts.append(docker.types.Mount(
                            '/doorstep',
                            ltldoorstep_root_dir,
                            type='bind'
                        ))

                    try:
                        ctr = client.containers.run(
                            '%s:%s' % (docker_image, docker_revision),
                            environment=envs,
                            mounts=mounts,
                            user=os.getuid(),
                            network_mode='none',
                            cap_drop='ALL',
                            detach=True
                        )
                    except docker.errors.ContainerError as error:
                        doorstep_exception = LintolDoorstepContainerException(
                            error,
                            processor=docker_image
                        )
                        raise doorstep_exception

                    adkr = aiodocker.Docker()
                    actr = await adkr.containers.get(ctr.name)
                    await actr.wait()
                    await adkr.close()

            reports = []
            for report_file in report_files:
                with open(report_file, 'r') as report_f:
                    reports.append(Report.load(report_f))

            report = combine_reports(*reports)

        return report

    @contextmanager
    def make_session(self):
        """Set up a workflow session.

        This creates a self-contained set of dask constructs representing our operation.
        """

        name = 'doorstep-%s' % str(uuid.uuid4())

        session = {
            'name': name,
            'queue': asyncio.Queue()
        }

        yield session
