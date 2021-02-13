"""Check dask threaded engine is correctly functioning."""

import json
import logging
from unittest.mock import Mock, patch, mock_open
import pytest
import asyncio
import asynctest
from ltldoorstep.engines.docker import DockerEngine
from ltldoorstep.processor import DoorstepProcessor
from ltldoorstep.reports.tabular import TabularReport

import logging

@pytest.fixture
def engine():
    """Create a threaded dask engine."""

    eng = DockerEngine()

    return eng

class TestProcessor(DoorstepProcessor):
    preset = 'tabular'
    code = 'testing-processor'

    def ret(self, r, filename, metadata):
        r.add_issue(logging.ERROR, 'foo-bar', filename)

    def get_workflow(self, filename, metadata):
        return {'output': (self.ret, self._report, filename, metadata)}

def test_can_run_workflow(engine):
    """Check we can run a workflow on local files."""

    filename = '/tmp/foo.csv'
    module = '/tmp/bar.py'
    metadata = {
        'lang': 'C.UTF-8',
        'definitions': {
            '0000': {
                'definition': {
                    'docker': {
                        'image': 'x',
                        'revision': 'y'
                    }
                }
            }
        },
        'supplementary': {
            'test': 'http://example.org'
        }
    }

    report = TabularReport('testing-processor', 'blank')
    report.add_issue(logging.ERROR, 'testing-processor', 'test')
    mopen = mock_open(read_data=json.dumps(report.compile()))
    docker = Mock()
    requests = Mock()
    request = Mock()
    request.status_code = 200

    requests.get.return_value = request
    request.iter_content.return_value = [
        '{\n',
        '   "report": "value"\n',
        '}\n'
    ]

    loop = asyncio.get_event_loop()
    session = {}
    adkr = Mock()
    actr = Mock()
    actr.wait = asynctest.CoroutineMock()
    adkr.close = asynctest.CoroutineMock()
    adkr.containers.get = asynctest.CoroutineMock(return_value=actr)
    aiodocker = Mock(return_value=adkr)

    with patch('ltldoorstep.engines.docker.open', mopen) as _, \
            patch('ltldoorstep.engines.docker.aiodocker.Docker', aiodocker), \
            patch('ltldoorstep.engines.docker.docker', docker), \
            patch('ltldoorstep.engines.docker.requests', requests):
        engine.add_processor({'test-processor': 'import python'}, metadata, session)
        report = loop.run_until_complete(engine.run(filename, module, metadata))

    result = report.__serialize__()
    assert result['tables'][0]['errors'][0]['processor'] == 'testing-processor'
