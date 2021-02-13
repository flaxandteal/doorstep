"""Check dask distributed engine is correctly functioning."""

from unittest.mock import Mock, patch, mock_open
from distributed import utils
from distributed import utils_test
import asyncio
import pytest
from ltldoorstep.engines.dask_distributed import DaskDistributedEngine
from contextlib import contextmanager
import gettext


@pytest.fixture
def engine():
    """Create a distributed dask engine."""

    eng = DaskDistributedEngine()
    gettext.install('ltldoorstep')

    return eng

@pytest.mark.skip
def test_can_run_workflow(engine):
    """Check we can run a workflow on local files."""

    filename = '/tmp/foo.csv'
    module = '/tmp/bar.py'
    metadata = {}

    test_module = '''
from ltldoorstep.processor import DoorstepProcessor
import logging

class TestProcessor(DoorstepProcessor):
    code = 'testing-processor'
    preset = 'geojson'

    def get_workflow(self, filename, metadata):
        return {'output': (ret, self._report, filename, metadata)}

processor = TestProcessor.make

def ret(r, filename, metadata):
    r.add_issue(logging.ERROR, 'foo-bar', filename.upper())

    '''

    mopen = mock_open(read_data=test_module)
    loop = asyncio.get_event_loop()

    with patch('distributed.client.open', mopen) as _:
        # Note that the event loop is handled within utils_test
        @utils_test.gen_cluster(client=True)
        async def _exec(c, s, a, b):
            engine.client = c
            return await engine.run(filename, module, metadata)

        result = _exec()

    assert result['tables'][0]['errors'][0]['message'] == filename.upper()
