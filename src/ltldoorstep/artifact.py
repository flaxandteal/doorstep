from dataclasses import dataclass

@dataclass
class ArtifactType:
    '''Class for tracking a (potential) artifact's nature'''
    is_bytes: bool
    mime: str = None
    encoding: str = 'utf-8'


@dataclass
class ArtifactRecord:
    '''Class for tracking an actual artifact'''
    uri: str
    is_bytes: bool
    mime: str = None
    encoding: str = 'utf-8'
