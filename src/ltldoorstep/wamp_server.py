from autobahn.asyncio.wamp import ApplicationRunner, ApplicationSession
from autobahn.wamp.types import PublishOptions
import sys
import traceback
import time
import requests
import docker
from urllib.parse import urlparse
import asyncio
import json
import logging
from autobahn.wamp.types import RegisterOptions
from collections import OrderedDict
from contextlib import contextmanager
import os
import uuid
import chardet
from .ini import DoorstepIni
from .errors import LintolDoorstepException

RECONNECT_DELAY = 6
TIMEOUT_TO_JOIN = 20

class SessionSet(OrderedDict):
    def __init__(self, engine):
        self._engine = engine

    def add(self):
        session = self._engine.make_session()

        ssn = session.__enter__()
        ssn['__context__'] = session

        self[ssn['name']] = ssn

        return ssn

    def __enter__(self):
        return self

    def __exit__(self, exctyp, excval, exctbk):
        exceptions = []
        for session in self.values():
            try:
                session['__context__'].__exit__(exctyp, excval, exctbk)
            except Exception as e:
                exceptions.append(e)

        if exceptions:
            raise RuntimeError(exceptions)

def make_session_set(engine):
    sessions = SessionSet(engine)
    try:
        yield sessions
    finally:
        sessions.clear()

class ProcessorResource():
    def __init__(self, engine, config):
        self._engine = engine
        self._config = config

    async def post(self, modules, ini, session):
        processors = {}
        if len(modules):
            for module, content in modules.items():
                processors[module] = content.encode('utf-8')

        ini = DoorstepIni.from_dict(ini)

        return self._engine.add_processor(processors, ini, session)

    async def action(self, action, processor_tag, processor_definition, session):
        logging.warn(_("Action posted"))
        logging.warn(processor_tag)
        logging.warn(str(processor_definition))
        logging.warn(action)

        return await self._engine.process_action(processor_tag, processor_definition, action)

class DataResource():
    def __init__(self, engine, config):
        self._engine = engine
        self._config = config

    async def post(self, filename, content, redirect, session=None):
        logging.warn(_("Data posted"))
        if redirect and self._engine.download():
            if content.startswith('file://'):
                with open(content[len('file://'):], 'r') as file_obj:
                    content = file_obj.read()
            else:
                r = requests.get(content, stream=True)
                logging.warn(_("Downloading %s") % content)

                if r.status_code != 200:
                    raise RuntimeError(_("Could not retrieve data from redirected URL: %d") % r.status_code)

                content = b''
                for chunk in r.iter_content(chunk_size=1024):
                    content += chunk

                if r.encoding:
                    encoding = r.encoding
                else:
                    encoding = chardet.detect(content)['encoding']

                try:
                    content = content.decode(encoding).encode('utf-8')
                except: # Get correct encoding error
                    logging.warn(_("Could not recode content from {} to UTF-8").format(encoding))
                    pass

        return self._engine.add_data(filename, content, redirect, session)

class ReportResource():
    def __init__(self, engine, config):
        self._engine = engine
        self._config = config

    async def get(self, session):
        result = await self._engine.get_output(session)
        result = result.__serialize__()
        result_string = json.dumps(result)

        if len(result_string) > self._config['report']['max-length-chars']:
            raise RuntimeError(_("Report is too long: %d characters") % len(result_string))

        return result_string

class DoorstepComponent(ApplicationSession):
    def __init__(self, engine, sessions, config, debug, join_timeout, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._id = 'ltlwc-%s' % str(uuid.uuid4())
        self._engine = engine
        self._sessions = sessions
        self._config = config
        self._debug = debug

        self._resource_processor = ProcessorResource(self._engine, self._config)
        self._resource_data = DataResource(self._engine, self._config)
        self._resource_report = ReportResource(self._engine, self._config)

        self._join_timeout = join_timeout

    def get_session(self, name):
        return self._sessions[name]

    def make_session(self):
        return self._sessions.add()

    async def wrap_register(self, endpoint, callback):
        uri = 'com.ltldoorstep.{server}.{endpoint}'.format(server=self._id, endpoint=endpoint)
        logging.warn(uri)

        async def _routine(session, *args, **kwargs):
            try:
                result = await callback(*args, session=self.get_session(session), **kwargs)
            except LintolDoorstepException as e:
                if self._debug:
                    exc_type, exc_value, exc_traceback = sys.exc_info()
                    traceback.print_tb(exc_traceback)
                raise e

            return result

        return await self.register(_routine, uri)

    async def onJoin(self, details):
        print("Joining")
        self._join_timeout.set_result(True)
        async def get_session_pair():
            session = self.make_session()
            print(_("Engaging for session %s") % session['name'])

            # Kick off observer coro
            try:
                __, monitor_output = await self._engine.monitor_pipeline(session)
                monitor_output = asyncio.ensure_future(monitor_output)
            except Exception as e:
                session['monitor_output'] = asyncio.sleep(1.0)
                return (self._id, session['name'])
            def output_results(output):
                logging.warn('outputting')
                return self.publish(
                    'com.ltldoorstep.event_result',
                    self._id,
                    session['name'],
                    options=PublishOptions(acknowledge=True)
                )

            monitor_output.add_done_callback(output_results)

            session['monitor_output'] = monitor_output

            return (self._id, session['name'])

        await self.register(
            get_session_pair,
            'com.ltldoorstep.engage',
            RegisterOptions(invoke='roundrobin')
        )
        await self.wrap_register('processor.post', self._resource_processor.post)
        await self.wrap_register('processor.action', self._resource_processor.action)
        await self.wrap_register('data.post', self._resource_data.post)
        await self.wrap_register('report.get', self._resource_report.get)

        async def status_retrieve():
            results = await self._engine.check_processor_statuses()

            incomplete_sessions = []
            for name, session in self._sessions.items():
                if 'completion' in session and not session['completion'].is_set():
                    incomplete_sessions.append(name)

            return self.publish(
                'com.ltldoorstep.status',
                self._id,
                results,
                incomplete_sessions,
                options=PublishOptions(acknowledge=True)
            )

        self.subscribe(status_retrieve, 'com.ltldoorstep.status-retrieve')

    def onDisconnect(self):
        logging.error(_("Disconnected from WAMP router"))
        asyncio.get_event_loop().stop()
        raise RuntimeError(_("Disconnected from WAMP router"))


def launch_wamp_real(engine, router='localhost:8080', config={}, debug=False):
    if not router.startswith('ws'):
        router = 'ws://%s/ws' % router

    with SessionSet(engine) as sessions:
        exit = False
        while not exit:
            loop = asyncio.get_event_loop()
            runner = ApplicationRunner(url=router, realm='realm1')

            if loop.is_closed():
                loop = asyncio.new_event_loop()
                print("New loop")
                asyncio.set_event_loop(loop)
                runner.transport_factory.loop = loop

            print("Start running")
            async def timeout(join_timeout):
                try:
                    await asyncio.wait_for(join_timeout, timeout=TIMEOUT_TO_JOIN)
                except asyncio.TimeoutError:
                    logging.error(_("Did not join WAMP router with {timeout}s").format(timeout=TIMEOUT_TO_JOIN))
                    asyncio.get_event_loop().stop()
                    raise RuntimeError(_("Did not join WAMP router with {timeout}s").format(timeout=TIMEOUT_TO_JOIN))

            async def start():
                join_timeout = asyncio.Future()

                asyncio.create_task(timeout(join_timeout))
                coro = runner.run(
                    lambda *args, **kwargs: DoorstepComponent(engine, sessions, config, debug, join_timeout, *args, **kwargs),
                    start_loop=False
                )
                await coro
            loop.run_until_complete(start())
            loop.run_forever()
            print(f"Run exited: waiting {RECONNECT_DELAY} seconds")
            time.sleep(RECONNECT_DELAY)

def launch_wamp(engine, router='#localhost:8080', config={}, debug=False):
    if router[0] == '#':
        router= router[1:]
        fallback = True
    else:
        fallback = False

    try:
        launch_wamp_real(engine, router, config, debug)
    except ConnectionRefusedError as e:
        if fallback:
            c = None
            try:
                print("No current WAMP router, starting one")
                client = docker.from_env()

                hostname, port = router.split(':')
                c = client.containers.run(
                    'crossbario/crossbar',
                    ports={
                        '8080/tcp': (hostname, port if port else 8080)
                    },
                    detach=True,
                    remove=True
                )
                time.sleep(3)
                launch_wamp_real(engine, router, config, debug)
            finally:
                if c:
                    print("[cleaning purpose-run WAMP router]")
                    c.stop()
        else:
            print("No current WAMP router found (tip: if you add a # at the front of the router URL, we'll try and start it for you).")
