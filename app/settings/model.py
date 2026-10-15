"""Application settings values; views receive separate display contracts."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ApiKeyEntry:
    name: str
    key: str


@dataclass(frozen=True)
class SettingsSnapshot:
    api_keys: tuple[ApiKeyEntry, ...] = ()
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    temperature: float = 0.7
    verify_ssl: bool = True
    width: int = 250
    height: int = 250
    always_on_top: bool = True
    max_memory_turns: int = 6
    history_limit: int = 20
    conversation_summary_enabled: bool = True
    reading_idle_seconds: int = 300
    selected_personality: str = "catgirl_companion"
    custom_personality: str = ""


class SettingsValidationError(ValueError):
    """Raised before persistence when settings contain invalid values."""
