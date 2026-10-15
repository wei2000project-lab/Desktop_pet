"""Settings view data, independent of Qt, persistence schemas and services.

Input values describe the form, not storage instructions. In particular, a blank
key or a changed source is interpreted by the application, never by this module.
Input conversion and display loading belong to the application layer.
"""
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
class GroupTestInputs:
    generation: int = 0
    targets: frozenset[tuple[str, str]] = frozenset()


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


@dataclass(frozen=True)
class LegacyKeyInput:
    name: str
    key: str = field(repr=False)


@dataclass(frozen=True)
class SettingsDisplay:
    """Application-provided values, without persistence paths or defaults policy."""

    api_keys: tuple[LegacyKeyInput, ...]
    base_url: str
    model: str
    temperature: float
    verify_ssl: bool
    width: int
    height: int
    always_on_top: bool
    max_memory_turns: int
    history_limit: int
    conversation_summary_enabled: bool
    reading_idle_seconds: int
    selected_personality: str
    custom_personality: str


@dataclass(frozen=True)
class APIKeyInput:
    id: str
    name: str
    key: str = field(repr=False)
    priority: int
    enabled: bool
    source: str
    key_edited: bool  # Current text differs from the initially displayed text.


@dataclass(frozen=True)
class APIGroupInput:
    id: str
    name: str
    base_url: str
    model: str
    temperature: float
    verify_ssl: bool
    auth_mode: str
    keys: tuple[APIKeyInput, ...]
    temperature_edited: bool


@dataclass(frozen=True)
class APIGroupsInput:
    """Full form snapshot; removed rows are absent, with no deletion policy here."""

    groups: tuple[APIGroupInput, ...]
    active_group_id: str | None


@dataclass(frozen=True)
class APIKeyDisplay:
    id: str
    name: str
    key: str = field(repr=False)
    priority: int
    enabled: bool
    source: str
    status: str = ""
    placeholder: str = ""


@dataclass(frozen=True)
class APIGroupDisplay:
    id: str
    name: str
    base_url: str
    model: str
    temperature: float
    verify_ssl: bool
    auth_mode: str
    keys: tuple[APIKeyDisplay, ...]


@dataclass(frozen=True)
class APIGroupsDisplay:
    groups: tuple[APIGroupDisplay, ...]
    active_group_id: str | None
    enabled: bool = True
    error: str | None = None


@dataclass(frozen=True)
class GroupFeedback:
    status: str
    completion_path_groups: frozenset[str]
    environment_available: bool
    key_statuses: dict[tuple[str, str], str] = field(default_factory=dict)
