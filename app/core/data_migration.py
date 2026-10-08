"""One-time, non-destructive migration of legacy runtime data."""
import configparser
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.core.paths import PROJECT_PATHS


LEGACY_RUNTIME_FILES = {
    "api.ini": "api.ini",
    "config.ini": "app.ini",
    "apps.json": "apps.json",
    "app_preferences.json": "preferences.json",
    "history.json": "history.json",
    "memory.json": "memory.json",
    "prompt.json": "prompt.json",
}


@dataclass(frozen=True)
class MigrationResult:
    migrated: tuple[str, ...]
    skipped: tuple[str, ...]
    failed: tuple[str, ...]


def migrate_legacy_runtime_data(
    legacy_dir: Path | str | None = None,
    runtime_dir: Path | str | None = None,
) -> MigrationResult:
    """Copy valid legacy files when the new destination does not exist.

    Legacy files are deliberately retained until manual validation is complete.
    """
    source_dir = Path(legacy_dir) if legacy_dir is not None else PROJECT_PATHS.legacy_config_dir
    destination_dir = Path(runtime_dir) if runtime_dir is not None else PROJECT_PATHS.runtime_dir
    destination_dir.mkdir(parents=True, exist_ok=True)
    migrated, skipped, failed = [], [], []

    for old_name, new_name in LEGACY_RUNTIME_FILES.items():
        source = source_dir / old_name
        destination = destination_dir / new_name
        if destination.exists() or not source.exists():
            skipped.append(new_name)
            continue

        temporary_path = None
        try:
            _validate_data_file(source)
            with tempfile.NamedTemporaryFile(
                dir=destination_dir,
                prefix=f".{new_name}.",
                suffix=".migration.tmp",
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
            shutil.copy2(source, temporary_path)
            _validate_data_file(temporary_path, expected_suffix=source.suffix)
            os.replace(temporary_path, destination)
            migrated.append(new_name)
        except (OSError, ValueError, json.JSONDecodeError, configparser.Error):
            failed.append(new_name)
        finally:
            if temporary_path and temporary_path.exists():
                try:
                    temporary_path.unlink()
                except OSError:
                    pass

    return MigrationResult(tuple(migrated), tuple(skipped), tuple(failed))


def _validate_data_file(path: Path, expected_suffix: str | None = None) -> None:
    suffix = expected_suffix or path.suffix
    if suffix.casefold() == ".json":
        with path.open("r", encoding="utf-8") as file:
            json.load(file)
        return
    if suffix.casefold() == ".ini":
        parser = configparser.ConfigParser()
        with path.open("r", encoding="utf-8") as file:
            parser.read_file(file)
        if not parser.sections():
            raise ValueError("INI file has no sections")
