from flask import current_app
from flask_restful import Resource, abort, reqparse
from ltldoorstep.engines import engines
from ltldoorstep.metadata import DoorstepContext
from ltldoorstep.config import load_config

import asyncio
import os

ENGINE = 'dask.threaded'
ENGINE_CONFIG = {}


class Handler(Resource):
    def post(self):
        parser = reqparse.RequestParser()
        parser.add_argument('filename', location='json')
        parser.add_argument('metadata', location='json')
        parser.add_argument('workflow', location='json')
        parser.add_argument('settings', location='json')
        args = parser.parse_args()

        engine = engines[ENGINE](config=ENGINE_CONFIG)

        metadata = args['metadata']
        if metadata is None:
            metadata = {}

        filename = args['filename']
        if filename is None:
            filename = ""

        workflow = args['workflow']
        if workflow is None:
            workflow = ""

        context_args = {'context': {'package': metadata}}

        if args['settings']:
            context_args['settings'] = args['settings']

        metadata = DoorstepContext.from_dict(context_args)

        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(engine.run(filename, workflow, metadata))

    @classmethod
    def preload(cls):
        if 'MINIO_BUCKET' in os.environ:
            self._bucket = os.environ['MINIO_BUCKET']

        if 'LINTOL_ENGINE' in os.environ:
            engine = os.environ['LINTOL_ENGINE']
        else:
            engine = 'dask.threaded'

        if 'LINTOL_PROCESSOR_DIRECTORY' in os.environ:
            workflow = None

            for f in os.listdir(os.environ['LINTOL_PROCESSOR_DIRECTORY']):
                if f.endswith('.py'):
                    workflow = f
                    break

            if not workflow:
                raise RuntimeError("No processor directory found: LINTOL_PROCESSOR_DIRECTORY has no python file")
        else:
            raise RuntimeError("No processor directory found: LINTOL_PROCESSOR_DIRECTORY must be set")

        logging.basicConfig(level=logging.DEBUG if debug else logging.INFO)
        cls.logger = logging.getLogger(__name__)
        cls.workflow = workfloW

    @classmethod
    def preload(cls):
        print("!!!")
        return True
