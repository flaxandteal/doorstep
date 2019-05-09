"""Engine for running a job, using dask, within this process."""

import uuid
import logging
from contextlib import contextmanager
from importlib.machinery import SourceFileLoader
from ..errors import LintolDoorstepException, LintolDoorstepContainerException
from ..reports.report import combine_reports
from ..file import make_file_manager
from ..encoders import json_dumps
from .dask_common import run as dask_run
from .engine import Engine
from asyncio import Lock, ensure_future, Queue
from ..ini import DoorstepIni


class DaskThreadedEngine(Engine):
    """Allow execution of a dask workflow within this process."""

    def add_data(self, filename, content, redirect, session):
        data = {
            'filename': filename,
            'content': content
        }
        logging.warn("Data added")
        ensure_future(session['queue'].put(data))

    def add_processor(self, modules, ini, session):
        if 'processors' not in session:
            session['processors'] = []

        if type(ini) is dict:
            ini = DoorstepIni.from_dict(ini)

        for uid, metadata in ini.definitions.items():
            filename = None
            content = None
            if metadata.module:
                filename = metadata.module
                if metadata.module in modules:
                    content = modules[metadata.module]
                else:
                    error_msg = _("Module content missing from processor %s") % metadata.module
                    logging.error(error_msg)
                    raise RuntimeError(error_msg)

            session['processors'].append({
                'name' : uid,
                'filename': filename,
                'content': content,
                'metadata': metadata
            })

        logging.warn("Processor added")

    async def monitor_pipeline(self, session):
        logging.warn("Waiting for processor and data")

        session['completion'] = Lock()

        async def run_when_ready():
            session['completion'].acquire()

            data = await session['queue'].get()

            try:
                result = await self.run_with_content(data['filename'], data['content'], session['processors'])
                session['result'] = result
            except Exception as error:
                if not isinstance(error, LintolDoorstepException):
                    error = LintolDoorstepException(error)
                session['result'] = error
            finally:
                session['completion'].release()

        ensure_future(run_when_ready())

        return (False, session['completion'].acquire())

    async def get_output(self, session):
        await session['completion'].acquire()

        print(session)
        result = session['result']

        session['completion'].release()

        if isinstance(result, LintolDoorstepException):
            raise result

        return result

    @staticmethod
    async def run_with_content(filename, content, processors):
        reports = []
        if type(content) == bytes:
            content = content.decode('utf-8')

        for processor in processors:
            workflow_module = processor['content']
            if type(workflow_module) == bytes:
                workflow_module = workflow_module.decode('utf-8')

            metadata = processor['metadata']
            print(processor, 'B')
            with make_file_manager(content={filename: content, processor['filename']: workflow_module}) as file_manager:
                print(file_manager.get(processor['filename']), processor['filename'], workflow_module, 'A')
                mod = SourceFileLoader('custom_processor', file_manager.get(processor['filename']))
                local_file = file_manager.get(filename)
                report = dask_run(local_file, mod.load_module(), metadata, compiled=False)
                reports.append(report)
        report = combine_reports(*reports)

        return report.compile(filename, {})

    @staticmethod
    async def run(filename, workflow_module, metadata, bucket=None):
        """Start the multi-threaded execution process."""

        mod = SourceFileLoader('custom_processor', workflow_module)

        result = None
        with make_file_manager(bucket) as file_manager:
            local_file = file_manager.get(filename)
            print('RUN')
            result = dask_run(local_file, mod.load_module(), metadata)

        return result

    @contextmanager
    def make_session(self):
        """Set up a workflow session.

        This creates a self-contained set of dask constructs representing our operation.
        """

        name = 'doorstep-%s' % str(uuid.uuid4())
        data_name = '%s-data' % name

        session = {
            'name': name,
            'data': data_name,
            'queue': Queue()
        }

        yield session
