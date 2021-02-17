"""Engine for running a job on an OpenFaaS cluster."""

from contextlib import contextmanager
import traceback
import aiohttp
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
ALLOWED_ACTIONS = ['restart']

def _check_allowed_functions(x, fn, allowed_functions):
    for tag, function in allowed_functions.items():
        if x == tag:
            return x, function

        # We allow matching by a pattern, between two slashes - in which case the OpenFaaS function
        # must also follow its own pattern, and match the context.docker['image'] (an abuse, as this
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

    async def run(self, filename, workflow_module, context, bucket=None):
        """Start the execution process over the cluster."""

        processors = [{
            'name': workflow_module,
            'context': context,
            'filename': filename,
            'content': filename
        }]

        target = 'doorstep/doorstep-no-session-%s' % str(uuid.uuid4())
        report = await self._run(filename, filename, processors, self.openfaas_host, self.openfaas_cred, self.allowed_functions, target=target)
        return report.compile(filename, context)

    async def monitor_pipeline(self, session):
        session['completion'] = asyncio.Event()

        async def run_when_ready():
            # await session['completion'].acquire()
            data = await session['queue'].get()
            try:
                target = 'doorstep/{}'.format(session['name'])
                result = await self._run(data['filename'], data['content'], session['processors'], self.openfaas_host, self.openfaas_cred, self.allowed_functions, target=target)
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

        status_code = -1
        try:
            async with aiohttp.ClientSession() as session:
                if get:
                    method = session.get
                else:
                    method = session.post

                async with method(
                            f'{openfaas_host}/function/{function}',
                            json=data,
                            auth=aiohttp.BasicAuth('admin', openfaas_cred)
                        ) as rq:
                    status_code = rq.status
                    text = await rq.text()
        except Exception as e:
            logging.error(_("OpenFaaS call threw exception"))
            logging.error(e)

            raise LintolDoorstepException(
                e,
                processor=processor_name,
                status_code=str(status_code)
            )

        try:
            content = json.loads(text)
        except Exception as e:
            logging.error(_("OpenFaaS call JSON decode failed"))
            logging.error(status_code)
            content = text
            logging.error(content)
            raise LintolDoorstepException(
                e,
                message=content,
                processor=processor_name
            )

        if 'error' in content and content['error']:
            try:
                exception = json.loads(content['exception'])
            except TypeError:
                exception = content['exception']

            if 'code' in exception:
                status_code = exception['code']
            else:
                status_code = status_code

            raise LintolDoorstepException(
                exception['exception'],
                processor=processor_name,
                message=exception['message'],
                status_code=str(status_code)
            )

        logging.error(str(content))
        return status_code, content

    @staticmethod
    async def _get_functions(openfaas_host, openfaas_cred, allowed_functions={}):
        status_code, content = await OpenFaaSEngine._make_openfaas_call(
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
        content = [
            [rev_functions[matched[cntt['name']]], cntt]
            for cntt in content
            if matched[cntt['name']]
        ]

        return content

    @staticmethod
    async def _run(filename, url, processors, openfaas_host, openfaas_cred, allowed_functions={}, target=None):
        reports = []
        for processor in processors:
            context = processor['context']

            tag, function = _check_allowed_functions(context.tag, context.docker['image'], allowed_functions)
            if not tag:
                tag, function = _check_allowed_functions(processor['name'], context.docker['image'], allowed_functions)

            if not tag:
                error_msg = _("Could not find {} or {} in allowed processors for OpenFaaS engine.").format(context.tag, processor['name'])
                error_msg += _("\nUpdate .ltldoorstep.yml to add more")
                raise RuntimeError(error_msg)

            if target:
                report_target = os.path.join(target, processor['name'])
            else:
                report_target = None
            data = {
                'filename': url,
                'workflow': tag,
                'target': report_target,
                'context': json.dumps(context.to_dict()),
            }

            status_code, content = await OpenFaaSEngine._make_openfaas_call(
                openfaas_host,
                openfaas_cred,
                function,
                data=data,
                processor_name=processor['name']
            )

            if status_code != 200:
                message = _("OpenFaaS call did not return status 200")

                logging.error(message)
                logging.error(content)

                try:
                    content = Report.parse(content)
                except:
                    pass

                raise LintolDoorstepException(
                    RuntimeError(_("OpenFaaS call did not return status 200")),
                    processor=processor['name'],
                    message=message + '\n\n' + str(content)
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

    async def process_action(self, processor_tag, processor_definition, action):
        tag, function = _check_allowed_functions(processor_tag, processor_definition['docker']['image'], self.allowed_functions)

        if not tag:
            error_msg = _("Could not find {} in allowed processors for OpenFaaS engine.").format(processor_tag)
            error_msg += _("\nUpdate .ltldoorstep.yml to add more")
            raise RuntimeError(error_msg)

        if action not in ALLOWED_ACTIONS:
            raise RuntimeError(_("Doorstep does not allow this action: {action}").format(action))

        status_code, content = await OpenFaaSEngine._make_openfaas_call(
            self.openfaas_host,
            self.openfaas_cred,
            'ltl-openfaas-manage',
            data={
                'function': function,
                'tag': tag,
                'action': action
            },
            processor_name=f'PROCESSOR-ACTION-{action.upper()}'
        )

        logging.info('%s %s', str(content), str(status_code))

        return content
