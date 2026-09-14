"""Canonical filesystem locations used by the application."""
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

ASSETS_DIR = PROJECT_ROOT / "assets"
LOGS_DIR = PROJECT_ROOT / "logs"

DATA_DIR = PROJECT_ROOT / "data"
CONFIG_DIR = DATA_DIR / "config"
APP_CONTROL_DATA_DIR = DATA_DIR / "app_control"
RUNTIME_DIR = DATA_DIR / "runtime"
