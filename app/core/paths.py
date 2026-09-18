"""Canonical filesystem locations used by the application."""
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

ASSETS_DIR = PROJECT_ROOT / "assets"
PET_ASSETS_DIR = ASSETS_DIR / "pet"
PET_ANIMATIONS_DIR = PET_ASSETS_DIR / "animations"
PET_EMOTIONS_DIR = PET_ASSETS_DIR / "emotions"
LOGS_DIR = PROJECT_ROOT / "logs"

DATA_DIR = PROJECT_ROOT / "data"
CONFIG_DIR = DATA_DIR / "config"
APP_CONTROL_DATA_DIR = DATA_DIR / "app_control"
RUNTIME_DIR = DATA_DIR / "runtime"
API_GROUPS_JSON_PATH = RUNTIME_DIR / "api_groups.json"
