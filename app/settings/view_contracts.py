"""Plain data exchanged between settings application code and its view."""
from dataclasses import dataclass, field
from enum import Enum


class CloseChoice(Enum):
    SAVE = "save"
    DISCARD = "discard"
    CANCEL = "cancel"


@dataclass
class CloseRequest:
    accepted: bool = True


@dataclass(frozen=True)
class ConnectionInputs:
    legacy_keys: dict[int, str] = field(default_factory=dict, repr=False)
    group_generation: int = 0
    group_targets: frozenset[tuple[str, str]] = frozenset()


@dataclass(frozen=True)
class TestTarget:
    kind: str
    row_id: int = 0
    group_id: str = ""
    key_id: str = ""
    generation: int = 0
