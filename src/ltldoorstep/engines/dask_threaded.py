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
import asyncio
from asyncio import Event, ensure_future, Queue
from ..ini import DoorstepIni
from ..config import examples_dir
import re
import os

def try_example_processor(processor_name):
    processor_file = re.sub(r'.*/([\w-]*):.*', r'\1', processor_name).replace('-', '_')
    processor_file = os.path.join(examples_dir(), f'{processor_file}.py')

    if os.path.exists(processor_file):
        return processor_file

    logging.warn(_('Could not find processor in examples: ') + processor_name)

    return False

class DaskThreadedEngine(Engine):
    """Allow execution of a dask workflow within this process."""

    def add_data(self, filename, content, redirect, session):
        data = {
            'filename': filename,
            'content': content
        }
        # logging.warn("Data added")
        ensure_future(session['queue'].put(data))

    def add_processor(self, modules, ini, session):

        if 'processors' not in session:
            session['processors'] = []

        if type(ini) is dict:
            ini = DoorstepIni.from_dict(ini)

        for uid, context in ini.definitions.items():
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

        logging.warn("Processor added")

    async def monitor_pipeline(self, session):
        logging.warn("Waiting for processor and data")

        session['completion'] = Event()

        # currently crashing here for a large dataset....
        async def run_when_ready():
            #session['completion'].acquire()
            # error here
            # session doesn't seem to be yielding before it crashes
            data = await session['queue'].get()
            logging.warn('Session var here after data is set %s' % session['queue'])
            if data == 0:
                logging.warn("Releasing session")
                session['completion'].set()
            try:
                result = await self.run_with_content(data['filename'], data['content'], session['processors'])
                session['result'] = result
            except Exception as error:
                if not isinstance(error, LintolDoorstepException):
                    error = LintolDoorstepException(error)
                session['result'] = error
            finally:
                session['completion'].set()
        ensure_future(run_when_ready())

        return (False, session['completion'].wait())

    async def get_output(self, session):
        await session['completion'].wait()

        result = session['result']

        if isinstance(result, LintolDoorstepException):
            print(result.__serialize__())
            raise result

        return result

    @staticmethod
    async def run_with_content(filename, content, processors):
        reports = []
        # if type(content) == bytes:
        #     content = content.decode('utf-8')

        for processor in processors:
            workflow_module = processor['content']
            if type(workflow_module) == bytes:
                workflow_module = workflow_module.decode('utf-8')

            context = processor['context']
            if not filename:
                filename = 'data.file'

            if processor['filename']:
                processor_filename = processor['filename']
            else:
                processor_filename = 'processor.py'

            with make_file_manager(content={filename: content, processor_filename: workflow_module}) as file_manager:
                if workflow_module:
                    mod = file_manager.get(processor_filename)
                else:
                    mod = try_example_processor(context.tag)
                    if not mod:
                        raise RuntimeError(_("The requested processor had no body, nor was an example processor."))

                mod = SourceFileLoader('custom_processor', mod)
                local_file = file_manager.get(filename)
                report = dask_run(local_file, mod.load_module(), context, compiled=False)
                reports.append(report)
        report = combine_reports(*reports)

        return report

    @staticmethod
    async def run(filename, workflow_module, context, bucket=None):
        """Start the multi-threaded execution process."""

        mod = SourceFileLoader('custom_processor', workflow_module)

        result = None
        with make_file_manager(bucket) as file_manager:
            local_file = file_manager.get(filename)
            result = dask_run(local_file, mod.load_module(), context)
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
        logging.warn("Yeiling session - %s " % session)
        yield session
