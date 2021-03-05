import configparser
import io
import logging
import os
import json
import collections
import yaml

try:
    from minio import Minio
    from minio.error import MinioException
except ImportError:
    Minio = None
    MinioException = RuntimeError

_config = {}
_active_config = {}

def set_config(key, value):
    global _active_config

    keys = key.split('.')

    level = _active_config
    for k in keys[:-1]:
        if k not in level:
            level[k] = {}
        level = level[k]

    level[keys[-1]] = value

def load_config():
    global _config, _active_config

    config = {
        'report': {
            'max-length-chars': 500000
        },
        'engine': {
            'openfaas': {
                'allowed-functions': {
                    'datatimes/dt-classify-category:1': 'ltl-datatimes-dt-classify-category',
                    'datatimes/dt-classify-location:1': 'ltl-datatimes-dt-classify-location',
                    'datatimes/dt-comprehender:1': 'ltl-datatimes-dt-comprehender'
                }
            }
        }
    }

    try:
        with open(os.path.join(os.path.expanduser("~"), '.ltldoorsteprc.yaml'), 'r') as config_file:
            config.update(yaml.load(config_file, Loader=yaml.SafeLoader))
    except IOError:
        logging.info(_("No config file found"))

    config.update(_config)
    _active_config = config

    return config

_mo = None
def load_from_minio(prefix, location):
    global _mo, _active_config
    config = _active_config

    path = os.path.join('/tmp', 'minio', location)
    if os.path.exists(path):
        return path

    if _mo is None:
        _mo = Minio(
            config['storage']['minio']['endpoint'],
            access_key=config['storage']['minio']['key'],
            secret_key=config['storage']['minio']['secret'],
            region=config['storage']['minio']['region'],
            secure=True
        )
    mo_bucket = config['storage']['minio']['bucket']

    try:
        data_object = _mo.get_object(mo_bucket, f'{prefix}/{location}')
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as f:
            for d in data_object.stream(32*1024):
                f.write(d)
    except MinioException as err:
        raise err

    return path


def load_reference_data(location):
    global _active_config
    config = _active_config

    path = location

    if 'reference-data' in config:
        if 'storage' in config['reference-data'] and config['reference-data']['storage'] == 'minio':
            path = load_from_minio(config['reference-data']['prefix'], location)

    return path

def examples_dir():
    import ltldoorstep_examples
    return os.path.dirname(ltldoorstep_examples.__file__)
