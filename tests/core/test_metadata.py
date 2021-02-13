"""Testing for metadata functionality"""
import pytest
from ltldoorstep.context import DoorstepContext
import logging


def test_can_create_metadata():
    """testing to see if we can create metadata objects"""

    metadata = DoorstepContext("image", "revision", docker_image="test", docker_revision="3")
    # assert metadata.docker["image"] == "image"
    assert metadata.docker["image"] == "test"
    # assert metadata.docker["revision"] == "revision"
    assert metadata.docker["revision"] == "3"
    # assert metadata.package == {"test": 3}
    assert metadata.package is None

def test_can_convert_metadata_to_dict():
    """testing to see if we can create metadata objects"""
    metadata = DoorstepContext(docker_image="image", docker_revision="revision", context_package="{test: 3}")
    assert metadata.to_dict() == {
        'definition': {
            'docker': {
                'image': 'image',
                'revision': 'revision'
            }
        },
        'lang': None,
        'context': {
            'package': "{test: 3}",
            'resource': 'null',
            'format': None
        },
        'settings': {},
        'configuration': {},
        'supplementary': None,
        'tag': None,
        'module': None,
    }

def test_can_set_package():
    """testing to see if setting package works"""
    metadata = DoorstepContext("image", "revision")
    metadata.package = "{\"test\": 3}"
    assert metadata.package == {"test": 3}
