from werkzeug.datastructures import FileStorage
import threading
import concurrent
import uuid
import asyncio
import json
from flask import Flask
import os
from flask_restful import Resource, Api, reqparse

app = Flask(__name__)
api = Api(app)

processors = {}
def loop_thread(loop):
    asyncio.set_event_loop(loop)
    loop.run_forever()

def get_session(session_id):
    if session_id and (session := app.sessions.get(session_id)):
        return session
    session = app.engine.make_session().__enter__()
    app.sessions[session["name"]] = session
    return session

class Processor(Resource):
    def post(self):
        asyncio.set_event_loop(app.loop)
        parse = reqparse.RequestParser()
        parse.add_argument('_session', type=str, location='form')
        parse.add_argument('script', type=FileStorage, location='files', action='append')
        parse.add_argument('module', type=str, action='append', location='form')
        parse.add_argument('ini', location='form')
        args = parse.parse_args()

        modules = {}
        if args['script']:
            for script in args['script']:
                content = script.read()
                filename = script.filename
                module_name = os.path.splitext(os.path.basename(filename))[0]
                modules[module_name] = content
        if args['module']:
            for filename in args['module']:
                if not os.path.isabs(filename):
                    cwd = os.path.abspath(os.getcwd())
                    filename = os.path.abspath(os.path.join(cwd, filename))
                    if not filename.startswith(cwd):
                        raise RuntimeError(
                            f"Module Python files must live in the server's current working directory: {filename}"
                        )

                module_name = os.path.splitext(os.path.basename(filename))[0]
                if module_name == "processor":
                    module_name = os.path.basename(os.path.dirname(filename))
                with open(filename) as module_f:
                    # We could cache these, but for now loading-on-demand of single-file Python modules in a
                    # batch process is not unreasonable.
                    modules[module_name] = module_f.read()
        ini = json.loads(args['ini'])

        session_id = args['_session']
        session = get_session(session_id)

        app.loop.call_soon_threadsafe(app.engine.add_processor, modules, ini, session)
        return {"status": "Success", "_session": session["name"]}


class Data(Resource):
    def post(self):
        asyncio.set_event_loop(app.loop)
        parse = reqparse.RequestParser()
        parse.add_argument('_session', type=str, location='form')
        parse.add_argument('content', type=FileStorage, location='files')
        parse.add_argument('redirect', type=bool, location='form')
        args = parse.parse_args()

        content = args['content'].read()
        filename = args['content'].filename
        redirect = args['redirect']

        session_id = args['_session']
        session = get_session(session_id)

        app.loop.call_soon_threadsafe(app.engine.add_data, filename, content, redirect, session)
        return {"status": "Success", "_session": session["name"]}

async def _monitor_pipeline(fut, session):
    _, completion = await app.engine.monitor_pipeline(session)
    await completion
    fut.set_result(session["result"])

class Report(Resource):
    def get(self):
        asyncio.set_event_loop(app.loop)
        fut = concurrent.futures.Future()

        parse = reqparse.RequestParser()
        parse.add_argument('_session', type=str, location='args')
        args = parse.parse_args()

        session_id = args['_session']
        session = app.sessions[session_id]

        app.loop.call_soon_threadsafe(asyncio.ensure_future, _monitor_pipeline(fut, session))
        concurrent.futures.wait([fut])

        result = fut.result()
        result = result.__serialize__()

        del app.sessions[session_id]
        return result

api.add_resource(Processor, '/processor')
api.add_resource(Data, '/data')
api.add_resource(Report, '/report')

def launch_flask(engine):
    loop = asyncio.get_event_loop()
    app.sessions = {}
    app.engine = engine
    app.loop = loop
    thread = threading.Thread(target=loop_thread, args=(loop,))
    thread.start()
    app.run()
