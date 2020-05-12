from dataclasses import dataclass

@dataclass
class ArtifactType:
    '''Class for tracking a (potential) artifact's nature'''
    mime: str = None
    is_bytes: bool


@dataclass
class ArtifactRecord:
    '''Class for tracking an actual artifact'''
    uri: str
    mime: str = None
    is_bytes: bool
