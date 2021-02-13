import json

class Serializable:
    def __serialize__(self):
        return str(self)

class DoorstepJSONEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Serializable):
            return o.__serialize__()

        return json.JSONEncoder.default(self, o)

json_dumps = lambda *args, **kwargs: json.dumps(*args, **kwargs, cls=DoorstepJSONEncoder)
