"""Canonical locations for bundled assets and current user-owned data.

Callers can supply another root in tests without changing global constants.
"""
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProjectPaths:
    project_root: Path
    runtime_root: Path | None = None
    categorized_data: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "project_root", Path(self.project_root))
        if self.runtime_root is not None:
            object.__setattr__(self, "runtime_root", Path(self.runtime_root))

    @property
    def data_dir(self) -> Path:
        return self.project_root / "data"

    @property
    def config_dir(self) -> Path:
        return self.data_dir / "config"

    @property
    def app_control_dir(self) -> Path:
        return self.data_dir / "app_control"

    @property
    def runtime_dir(self) -> Path:
        return self.runtime_root if self.runtime_root is not None else self.data_dir / "runtime"

    @property
    def logs_dir(self) -> Path:
        return self.project_root / "logs"

    @property
    def default_app_ini(self) -> Path:
        return self.config_dir / "app.defaults.ini"

    @property
    def default_prompt_json(self) -> Path:
        return self.config_dir / "prompt.json"

    @property
    def app_aliases_json(self) -> Path:
        return self.app_control_dir / "aliases.json"

    @property
    def app_ini(self) -> Path:
        return (self.config_dir if self.categorized_data else self.runtime_dir) / "app.ini"

    @property
    def legacy_api_ini(self) -> Path:
        return self.runtime_dir / "api.ini"

    @property
    def api_groups_json(self) -> Path:
        return (self.config_dir if self.categorized_data else self.runtime_dir) / "api_groups.json"

    @property
    def prompt_json(self) -> Path:
        return (self.config_dir / "prompt.user.json") if self.categorized_data else (self.runtime_dir / "prompt.json")

    @property
    def tools_json(self) -> Path:
        return (self.config_dir if self.categorized_data else self.runtime_dir) / "tools.json"

    @property
    def history_json(self) -> Path:
        return self.runtime_dir / "history.json"

    @property
    def memory_json(self) -> Path:
        return self.runtime_dir / "memory.json"

    @property
    def preferences_json(self) -> Path:
        return (self.app_control_dir if self.categorized_data else self.runtime_dir) / "preferences.json"

    @property
    def apps_json(self) -> Path:
        return (self.app_control_dir if self.categorized_data else self.runtime_dir) / "apps.json"

    @property
    def env_file(self) -> Path:
        return (self.config_dir if self.categorized_data else self.project_root) / ".env"

    @property
    def legacy_config_dir(self) -> Path:
        return self.project_root / "config"

    @property
    def app_log(self) -> Path:
        return self.logs_dir / "app.log"


PROJECT_ROOT = Path(__file__).resolve().parents[2]
# Existing user data has been copied and verified in the categorized locations.
PROJECT_PATHS = ProjectPaths(PROJECT_ROOT, categorized_data=True)

ASSETS_DIR = PROJECT_ROOT / "assets"
PET_ASSETS_DIR = ASSETS_DIR / "pet"
PET_ANIMATIONS_DIR = PET_ASSETS_DIR / "animations"
PET_EMOTIONS_DIR = PET_ASSETS_DIR / "emotions"
LOGS_DIR = PROJECT_PATHS.logs_dir

DATA_DIR = PROJECT_PATHS.data_dir
CONFIG_DIR = PROJECT_PATHS.config_dir
APP_CONTROL_DATA_DIR = PROJECT_PATHS.app_control_dir
RUNTIME_DIR = PROJECT_PATHS.runtime_dir
API_GROUPS_JSON_PATH = PROJECT_PATHS.api_groups_json
