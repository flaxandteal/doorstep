import json
import logging

class DoorstepContext:
    def __init__(self, lang=None, tag=None, module=None, docker_image=None, docker_revision=None, context_package=None, settings={}, configuration={}, supplementary=None, context_format=None, context_resource=None):
        self.lang = lang
        self.docker = {
            'image': docker_image,
            'revision': docker_revision
        }
        self.tag = tag
        self.module = module
        self.package = context_package
        self.resource = context_resource
        self.settings = settings
        self.configuration = configuration
        self.supplementary = supplementary
        self.context_format = context_format

    def __repr__(self):
        return "<DoorstepContext: {}>".format(self.to_dict())

    def has_package(self):
        return bool(self.package)

    def has_resource(self):
        return bool(self.resource)

    def get_setting(self, setting, default=None):
        if setting in self.configuration:
            return self.configuration[setting]
        if setting in self.settings:
            return self.settings[setting]
        return default

    @property
    def resource(self):
        resource = self._context_resource

        if type(resource) is str:
            resource = json.loads(resource)
            self._context_resource = resource

        return resource

    @property
    def package(self):
        package = self._context_package

        if type(package) is str:
            package = json.loads(package)
            self._context_package = package

        return package

    @package.setter
    def package(self, package):
        self._context_package = package

    @resource.setter
    def resource(self, resource):
        self._context_resource = resource

    @classmethod
    def from_dict(cls, dct):
        kwargs = {}

        if 'tag' in dct:
            kwargs['tag'] = dct['tag']

        if 'module' in dct:
            kwargs['module'] = dct['module']

        if 'definition' in dct and 'docker' in dct['definition']:
            kwargs['docker_image'] = dct['definition']['docker']['image']
            kwargs['docker_revision'] = dct['definition']['docker']['revision']

        if 'context' in dct:
            if 'package' in dct['context'] and dct['context']['package']:
                kwargs['context_package'] = dct['context']['package']
            if 'resource' in dct['context'] and dct['context']['resource']:
                kwargs['context_resource'] = dct['context']['resource']
            if 'format' in dct['context'] and dct['context']['format']:
                kwargs['context_format'] = dct['context']['format']

        if 'settings' in dct:
            kwargs['settings'] = dct['settings']

        if 'configuration' in dct:
            kwargs['configuration'] = dct['configuration']

        if 'supplementary' in dct:
            kwargs['supplementary'] = dct['supplementary']

        if 'lang' in dct:
            kwargs['lang'] = dct['lang']

        return cls(**kwargs)

    def to_dict(self):
        package = self._context_package
        if type(package) is not str:
            package = json.dumps(package)

        resource = self._context_resource
        if type(resource) is not str:
            resource = json.dumps(resource)

        return {
            'definition': {
                'docker': dict(self.docker)
            },
            'lang': self.lang,
            'context': {
                'package': package,
                'resource': resource,
                'format': self.context_format
            },
            'settings': dict(self.settings),
            'configuration': dict(self.configuration),
            'supplementary': dict(self.supplementary) if self.supplementary else None,
            'tag': self.tag,
            'module': self.module
        }
