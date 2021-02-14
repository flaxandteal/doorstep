import json
import logging
import abc
from typing import Optional, Dict

from .encoders import Serializable

class Aspect(Serializable):
    _aspect: Optional[str] = None

    def __serialize__(self):
        definition = {
            '_aspect': self._aspect,
            'plaintext': self.plaintext
        }
        definition.update(self.render())
        return definition

    def __init__(self, plaintext):
        self._plaintext = str(plaintext)

    @property
    def plaintext(self):
        return self._plaintext

    @abc.abstractmethod
    def render(self):
        return

    def __str__(self):
        return json.dumps(self.__serialize__())

# Within the definition of an aspect, it may
# be _either_ a simple Unicode string, _or_
# a JSON object with an '_aspect' member.
class RawTextAspect(Aspect):
    _aspect = '(raw)'

    def render(self):
        return self._plaintext

    def __serialize__(self):
        return str(self.render())

# This is equivalent to the raw text aspect,
# but in a full aspect structure.
class PlaintextAspect(Aspect):
    _aspect = 'plaintext'

    def render(self):
        return {}


class AnnotatedTextAspect(Aspect):
    _aspect = 'annotated'

    class Annotation:
        _for_aspect = None
        _note: str = ''
        _start_offset: int = 0
        _end_offset: int = 0

        level_tags: Dict[str, str] = {
            logging.INFO: 'INFO',
            logging.WARNING: 'WARNING',
            logging.ERROR: 'ERROR'
        }

        # FIXME
        level_tags_rev: Dict[str, str] = {
            'INFO': logging.INFO,
            'WARNING': logging.WARNING,
            'ERROR': logging.ERROR
        }

        def __init__(self, for_, note, start_offset, end_offset, level, tags=[]):
            self._for_aspect = for_
            self._note = note
            self._start_offset = start_offset
            self._end_offset = end_offset
            self.level = level

            if set(tags) & set(self.level_tags):
                raise RuntimeError("Annotation tags should have no loglevel tags")
            self._tags = set(tags)
            self._tags.add(self.level_tags[level])

        def render(self):
            return {
                "text": self._note, # optional content of annotation, if info should be shown
                "ranges": [ # list of ranges covered by annotation (usually only one entry)
                    {
                        "start": "/", # optional (relative) XPath to start element
                        "end": "/",   # optional (relative) XPath to end element
                        "startOffset": self._start_offset, # character offset within start element
                        "endOffset": self._end_offset      # character offset within end element
                    }
                ],
                "tags": sorted(self._tags, reverse=True)
            }

    def __init__(self, *args, **kwargs):
        self._annotations = []
        super().__init__(*args, **kwargs)

    def add(self, note, start_offset, end_offset, level, tags=[]):
        self._annotations.append(
            self.Annotation(
                for_=self,
                note=note,
                start_offset=start_offset,
                end_offset=end_offset,
                level=level,
                tags=tags
            )
        )

    def get_annotations(self):
        return self._annotations

    def render(self):
        return {
            'annotations': [ann.render() for ann in self._annotations]
        }

    @classmethod
    def parse(cls, item):
        aspect = cls(item['plaintext'])
        level_tags_rev = cls.Annotation.level_tags_rev
        for ann in item['annotations']:
            levels = set(level_tags_rev) & set(ann['tags'])
            if len(levels) > 0:
                level = level_tags_rev[next(iter(levels))]
                tags = list(set(ann['tags']) - set(level_tags_rev))
            else:
                level = logging.INFO

            aspect.add(
                note=ann['text'],
                start_offset=ann['ranges'][0]['startOffset'],
                end_offset=ann['ranges'][0]['endOffset'],
                level=level,
                tags=tags
            )
        return aspect

_ASPECTS = {asp._aspect: asp for asp in [
    PlaintextAspect,
    AnnotatedTextAspect
]}
def get_aspect_class(code):
    return _ASPECTS[code]

