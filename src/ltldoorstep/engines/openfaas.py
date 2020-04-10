"""Engine for running a job on an OpenFaaS cluster."""

from contextlib import contextmanager
import traceback
import requests
from requests.auth import HTTPBasicAuth
import re
import asyncio
import time
import os
import sys
import json
import uuid
import jinja2
import logging
from ..ini import DoorstepIni
from ..errors import LintolDoorstepException, LintolDoorstepContainerException
from concurrent.futures import ThreadPoolExecutor
from .engine import Engine
from ..reports.report import Report, combine_reports

OPENFAAS_HOST = 'http://127.0.0.1:8084'
FUNCTION_CONTAINER_PREFIX = '/home/user/.local/lib/python3.6/site-packages/'

def _check_allowed_functions(x, fn, allowed_functions):
    for tag, function in allowed_functions.items():
        if x == tag:
            return x, function

        # We allow matching by a pattern, between two slashes - in which case the OpenFaaS function
        # must also follow its own pattern, and match the metadata.docker['image'] (an abuse, as this
        # must then actually be the OpenFaaS function name, not the docker image for the function)
        if {tag[0], tag[-1]} == {'/'} and re.match(tag[1:-1], x) and fn:
            if {function[0], function[-1]} == {'/'} and re.match(function[1:-1], fn):
                return tag, fn
    return None, None


class OpenFaaSEngine(Engine):
    """Allow execution of workflows on a OpenFaaS cluster."""

    def download(self):
        return False

    def __init__(self, config=None):
        self.allowed_functions = {}

        if config and 'engine' in config:
            config = config['engine']

            self.openfaas_host = OPENFAAS_HOST
            self.openfaas_cred = ''

            if 'openfaas' in config:
                config = config['openfaas']
                if 'host' in config:
                    self.openfaas_host = config['host']

                if 'credential' in config:
                    self.openfaas_cred = config['credential']

                if 'allowed-functions' in config:
                    self.allowed_functions = config['allowed-functions']

    @staticmethod
    def description():
        return '(not provided)'

    @staticmethod
    def config_help():
        return None

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

    async def run(self, filename, workflow_module, metadata, bucket=None):
        """Start the execution process over the cluster."""

        processors = [{
            'name': workflow_module,
            'metadata': metadata,
            'filename': filename,
            'content': filename
        }]
        report = await self._run(filename, filename, processors, self.openfaas_host, self.openfaas_cred, self.allowed_functions)
        return report.compile(filename, metadata)

    async def monitor_pipeline(self, session):
        session['completion'] = asyncio.Event()

        async def run_when_ready():
            # await session['completion'].acquire()
            data = await session['queue'].get()
            try:
                result = await self._run(data['filename'], data['content'], session['processors'], self.openfaas_host, self.openfaas_cred, self.allowed_functions)
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

    async def check_processor_statuses(self):
        content = await self._get_functions(self.openfaas_host, self.openfaas_cred, self.allowed_functions)
        return content

    @staticmethod
    async def _make_openfaas_call(openfaas_host, openfaas_cred, function, get=False, data={}, processor_name=None):
        rq = None
        if get:
            method = requests.get
        else:
            method = requests.post

        try:
            rq = method(
                f'{openfaas_host}/function/{function}',
                json=data,
                auth=HTTPBasicAuth('admin', openfaas_cred)
            )
        except Exception as e:
            logging.error(_("OpenFaaS call threw exception"))
            logging.error(e)
            if rq:
                status_code = rq.status_code
            else:
                status_code = -1

            raise LintolDoorstepException(
                e,
                processor=processor_name,
                status_code=str(status_code)
            )

        try:
            content = json.loads(rq.content)
        except Exception as e:
            logging.error(_("OpenFaaS call JSON decode failed"))
            logging.error(rq.status_code)
            logging.error(rq.content)
            raise LintolDoorstepException(
                e,
                message=rq.content,
                processor=processor_name
            )

        if 'error' in content and content['error']:
            exception = json.loads(content['exception'])
            if 'code' in exception:
                status_code = exception['code']
            else:
                status_code = rq.status_code

            raise LintolDoorstepException(
                exception['exception'],
                processor=processor_name,
                message=exception['message'],
                status_code=str(status_code)
            )

        return rq, content

    @staticmethod
    async def _get_functions(openfaas_host, openfaas_cred, allowed_functions={}):
        rq, content = await OpenFaaSEngine._make_openfaas_call(
            openfaas_host,
            openfaas_cred,
            'ltl-openfaas-status',
            processor_name='STATUS-CHECKER'
        )

        rev_functions = {
            v: k
            for k, v in allowed_functions.items()
        }

        def _check_functions(x):
            if x in rev_functions:
                return x
            for fn in rev_functions:
                if {fn[0], fn[-1]} == {'/'} and re.match(fn[1:-1], x):
                    return fn
            return None

        matched = {cntt['name']: _check_functions(cntt['name']) for cntt in content}
        content = {
            rev_functions[matched[cntt['name']]]: cntt
            for cntt in content
            if matched[cntt['name']]
        }

        return content

    @staticmethod
    async def _run(filename, content, processors, openfaas_host, openfaas_cred, allowed_functions={}):
        reports = []
        for processor in processors:
            metadata = processor['metadata']

            tag, function = _check_allowed_functions(metadata.tag, metadata.docker['image'], allowed_functions)
            if not tag:
                tag, function = _check_allowed_functions(processor['name'], metadata.docker['image'], allowed_functions)

            if not tag:
                error_msg = _("Could not find {} or {} in allowed processors for OpenFaaS engine.").format(metadata.tag, processor['name'])
                error_msg += _("\nUpdate .ltldoorstep.yml to add more")
                raise RuntimeError(error_msg)

            data = {
                'filename': content,
                'workflow': tag,
                'metadata': json.dumps(metadata.to_dict()),
            }

            rq, content = await OpenFaaSEngine._make_openfaas_call(
                openfaas_host,
                openfaas_cred,
                function,
                data=data,
                processor_name=processor['name']
            )

            try:
                report = Report.parse(content)
            except Exception as e:
                logging.error(_("Could not parse report from OpenFaaS call"))
                logging.error(content)
                raise LintolDoorstepException(
                    e,
                    processor=processor['name']
                )

            reports.append(report)

        report = combine_reports(*reports)
        report.filename = filename

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
