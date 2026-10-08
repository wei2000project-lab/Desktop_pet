import os
import copy
import configparser
import io
import json
import tempfile
from pathlib import Path
from typing import Any, Dict, List

from app.ai.api_keys import decode_api_key_entries, encode_api_key_entries, first_api_key
from app.core.data_migration import migrate_legacy_runtime_data
from app.core.paths import PROJECT_PATHS, ProjectPaths
from app.utils.logger import logger


def read_layered_ini(default_path: Path | str, runtime_path: Path | str) -> configparser.ConfigParser:
    """Read tracked defaults first, then overlay user-owned runtime settings."""
    parser = configparser.ConfigParser()
    existing_paths = [str(path) for path in (default_path, runtime_path) if Path(path).exists()]
    if existing_paths:
        parser.read(existing_paths, encoding="utf-8")
    return parser


def read_layered_json(default_path: Path | str, runtime_path: Path | str) -> Dict[str, Any]:
    """Merge a tracked JSON object with user-owned runtime overrides."""
    merged: Dict[str, Any] = {}
    for path in (Path(default_path), Path(runtime_path)):
        merged.update(_read_json_object(path))
    return merged


def _read_json_object(path: Path | str) -> Dict[str, Any]:
    path = Path(path)
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as file:
        value = json.load(file)
    if not isinstance(value, dict):
        raise ValueError(f"JSON settings must contain an object: {path}")
    return value


def write_text_bundle_atomically(contents: Dict[Path | str, str]) -> None:
    """Replace multiple text files and restore earlier files if one replacement fails."""
    normalized = {Path(path): text for path, text in contents.items()}
    originals: Dict[Path, bytes | None] = {}
    temporary_paths: Dict[Path, Path] = {}
    replaced: List[Path] = []

    try:
        for path, text in normalized.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            originals[path] = path.read_bytes() if path.exists() else None
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temporary_file.write(text)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
                temporary_paths[path] = Path(temporary_file.name)

        for path, temporary_path in temporary_paths.items():
            os.replace(temporary_path, path)
            replaced.append(path)
    except Exception:
        for path in reversed(replaced):
            original = originals[path]
            try:
                if original is None:
                    path.unlink(missing_ok=True)
                else:
                    _replace_bytes_atomically(path, original)
            except OSError:
                logger.error("Failed to roll back settings file: %s", path, exc_info=True)
        raise
    finally:
        for temporary_path in temporary_paths.values():
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass


def _replace_bytes_atomically(path: Path, value: bytes) -> None:
    with tempfile.NamedTemporaryFile(
        mode="wb",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".rollback.tmp",
        delete=False,
    ) as temporary_file:
        temporary_file.write(value)
        temporary_file.flush()
        os.fsync(temporary_file.fileno())
        temporary_path = Path(temporary_file.name)
    try:
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _serialize_ini(parser: configparser.ConfigParser) -> str:
    buffer = io.StringIO()
    parser.write(buffer)
    return buffer.getvalue()


class ConfigManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConfigManager, cls).__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self, paths: ProjectPaths = PROJECT_PATHS):
        migration = migrate_legacy_runtime_data(
            legacy_dir=paths.legacy_config_dir,
            runtime_dir=paths.runtime_dir,
        )
        if migration.failed:
            logger.warning("Runtime data migration incomplete: %s", ", ".join(migration.failed))

        self._configure_paths(paths)

        self.general_config = configparser.ConfigParser()
        self.api_config = configparser.ConfigParser()

        self.load_env()
        self.load_configs()

    def _configure_paths(self, paths: ProjectPaths) -> None:
        """Set file locations without reading or creating data."""
        self.root_dir = str(paths.project_root)
        self.config_dir = str(paths.config_dir)
        self.default_config_ini_path = str(paths.default_app_ini)
        self.config_ini_path = str(paths.app_ini)
        self.api_ini_path = str(paths.legacy_api_ini)
        self.api_groups_json_path = str(paths.api_groups_json)
        self.default_prompt_json_path = str(paths.default_prompt_json)
        self.prompt_json_path = str(paths.prompt_json)
        self.tools_json_path = str(paths.tools_json)
        self.history_json_path = str(paths.history_json)
        self.memory_json_path = str(paths.memory_json)
        self.env_path = str(paths.env_file)

    def _tools_path(self) -> Path:
        return Path(self.tools_json_path)

    def load_env(self):
        """Loads simple key-value pairs from .env into os.environ if it exists."""
        if os.path.exists(self.env_path):
            logger.info("Loading .env file")
            with open(self.env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, val = line.split("=", 1)
                        os.environ[key.strip()] = val.strip()

    def load_configs(self):
        """Loads ini config files."""
        # General Config
        self.general_config = read_layered_ini(
            self.default_config_ini_path,
            self.config_ini_path,
        )
        if not self.general_config.has_section("General"):
            logger.warning("General config not found, using empty config")
            self.general_config.add_section("General")

        # API Config
        self.api_config = configparser.ConfigParser()
        if os.path.exists(self.api_ini_path):
            self.api_config.read(self.api_ini_path, encoding="utf-8")
        else:
            logger.warning("api.ini not found, using empty API config")
            self.api_config.add_section("API")

    # General Configuration Accessors
    def get_general(self, key: str, default: Any = None) -> Any:
        try:
            return self.general_config.get("General", key)
        except (configparser.NoSectionError, configparser.NoOptionError):
            return default

    def get_general_int(self, key: str, default: int = 0) -> int:
        try:
            return self.general_config.getint("General", key)
        except (configparser.NoSectionError, configparser.NoOptionError, ValueError):
            return default

    def get_general_float(self, key: str, default: float = 0.0) -> float:
        try:
            return self.general_config.getfloat("General", key)
        except (configparser.NoSectionError, configparser.NoOptionError, ValueError):
            return default

    def get_general_bool(self, key: str, default: bool = False) -> bool:
        try:
            return self.general_config.getboolean("General", key)
        except (configparser.NoSectionError, configparser.NoOptionError, ValueError):
            return default

    def set_general(self, key: str, value: Any):
        if not self.general_config.has_section("General"):
            self.general_config.add_section("General")
        self.general_config.set("General", key, str(value))
        self.save_general_config()

    def save_general_config(self):
        try:
            os.makedirs(os.path.dirname(self.config_ini_path), exist_ok=True)
            with open(self.config_ini_path, "w", encoding="utf-8") as f:
                self.general_config.write(f)
        except Exception as e:
            logger.error(f"Failed to save config.ini: {e}")

    # API Configuration Accessors
    def get_api(self, key: str, default: Any = None) -> Any:
        # First check environmental variable for API Key if requested
        if key.upper() == "APIKEY" or key.upper() == "API_KEY":
            env_key = os.environ.get("OPENAI_API_KEY")
            if env_key:
                return env_key
        
        try:
            val = self.api_config.get("API", key)
            if not val and (key.upper() == "APIKEY" or key.upper() == "API_KEY"):
                # Fallback to env variable if key is empty in ini file
                return os.environ.get("OPENAI_API_KEY", default)
            return val
        except (configparser.NoSectionError, configparser.NoOptionError):
            if key.upper() == "APIKEY" or key.upper() == "API_KEY":
                return os.environ.get("OPENAI_API_KEY", default)
            return default

    def set_api(self, key: str, value: Any):
        if not self.api_config.has_section("API"):
            self.api_config.add_section("API")
        self.api_config.set("API", key, str(value))
        self.save_api_config()

    def get_api_key_entries(self) -> List[Dict[str, str]]:
        raw_entries = ""
        legacy_key = ""
        try:
            raw_entries = self.api_config.get("API", "ApiKeys")
        except (configparser.NoSectionError, configparser.NoOptionError):
            raw_entries = ""
        try:
            legacy_key = self.api_config.get("API", "ApiKey")
        except (configparser.NoSectionError, configparser.NoOptionError):
            legacy_key = ""
        return decode_api_key_entries(raw_entries, legacy_key=legacy_key)

    def set_api_key_entries(self, entries: List[Dict[str, str]]):
        if not self.api_config.has_section("API"):
            self.api_config.add_section("API")
        encoded = encode_api_key_entries(entries)
        self.api_config.set("API", "ApiKeys", encoded)
        self.api_config.set("API", "ApiKey", first_api_key(entries))
        self.save_api_config()

    def get_active_api_key(self) -> str:
        env_key = os.environ.get("OPENAI_API_KEY")
        if env_key:
            return env_key
        return first_api_key(self.get_api_key_entries())

    def save_api_config(self):
        try:
            os.makedirs(os.path.dirname(self.api_ini_path), exist_ok=True)
            with open(self.api_ini_path, "w", encoding="utf-8") as f:
                self.api_config.write(f)
        except Exception as e:
            logger.error(f"Failed to save api.ini: {e}")

    def save_settings_bundle(
        self,
        general_values: Dict[str, Any],
        api_values: Dict[str, Any],
        api_key_entries: List[Dict[str, str]],
        prompt_values: Dict[str, Any],
        api_group_contents: str | None = None,
        preserve_legacy_api: bool = False,
    ) -> None:
        """Persist one complete settings edit, rolling back if any file fails."""
        general_config = copy.deepcopy(self.general_config)
        api_config = copy.deepcopy(self.api_config)
        if not general_config.has_section("General"):
            general_config.add_section("General")
        if not api_config.has_section("API"):
            api_config.add_section("API")

        for key, value in general_values.items():
            general_config.set("General", key, str(value))
        for key, value in api_values.items():
            api_config.set("API", key, str(value))
        if not preserve_legacy_api:
            api_config.set("API", "ApiKeys", encode_api_key_entries(api_key_entries))
            api_config.set("API", "ApiKey", first_api_key(api_key_entries))

        runtime_prompt: Dict[str, Any] = {}
        prompt_path = Path(self.prompt_json_path)
        if prompt_path.exists():
            with prompt_path.open("r", encoding="utf-8") as file:
                runtime_prompt = json.load(file)
            if not isinstance(runtime_prompt, dict):
                raise ValueError("Runtime prompt settings must contain an object")
        runtime_prompt.update(prompt_values)
        runtime_prompt.pop("personality_options", None)
        runtime_prompt.pop("custom_personality_enabled", None)

        contents = {
            Path(self.config_ini_path): _serialize_ini(general_config),
            prompt_path: json.dumps(runtime_prompt, ensure_ascii=False, indent=2) + "\n",
        }
        if not preserve_legacy_api:
            contents[Path(self.api_ini_path)] = _serialize_ini(api_config)
        if api_group_contents is not None:
            contents[Path(self.api_groups_json_path)] = api_group_contents
        write_text_bundle_atomically(contents)
        self.general_config = general_config
        self.api_config = api_config

    def get_api_group_contents(self) -> str | None:
        """Missing is distinct from corrupt; never create a group file on reads."""
        path = Path(self.api_groups_json_path)
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    def save_api_group_contents(self, contents: str) -> None:
        write_text_bundle_atomically({Path(self.api_groups_json_path): contents})

    def get_legacy_api_values(self) -> Dict[str, str]:
        """Stored values only, without environment overrides or forgiving key decoding."""
        if not self.api_config.has_section("API"):
            return {}
        return dict(self.api_config.items("API", raw=True))

    # JSON Handlers (Prompt, History, Memory)
    def get_prompt(self) -> Dict[str, Any]:
        prompt_data: Dict[str, Any] = {}
        try:
            prompt_data.update(_read_json_object(self.default_prompt_json_path))
        except Exception as e:
            logger.error(f"Failed to load default prompt settings: {e}")
        try:
            prompt_data.update(_read_json_object(self.prompt_json_path))
        except Exception as e:
            logger.error(f"Failed to load runtime prompt settings: {e}")
        return prompt_data

    def save_prompt(self, prompt_data: Dict[str, Any]):
        try:
            write_text_bundle_atomically(
                {
                    Path(self.prompt_json_path): json.dumps(prompt_data, ensure_ascii=False, indent=2) + "\n",
                }
            )
        except Exception as e:
            logger.error(f"Failed to save runtime prompt settings: {e}")

    def get_history(self) -> List[Dict[str, Any]]:
        if os.path.exists(self.history_json_path):
            try:
                with open(self.history_json_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load history.json: {e}")
        return []

    def save_history(self, history: List[Dict[str, Any]]):
        limit = self.get_general_int("HistoryLimit", 20)
        if len(history) > limit:
            history = history[-limit:]
        try:
            os.makedirs(os.path.dirname(self.history_json_path), exist_ok=True)
            with open(self.history_json_path, "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save history.json: {e}")

    def clear_history(self):
        self.save_history([])

    def get_memory(self) -> Dict[str, Any]:
        if os.path.exists(self.memory_json_path):
            try:
                with open(self.memory_json_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load memory.json: {e}")
        return {}

    def save_memory(self, memory: Dict[str, Any]):
        try:
            os.makedirs(os.path.dirname(self.memory_json_path), exist_ok=True)
            with open(self.memory_json_path, "w", encoding="utf-8") as f:
                json.dump(memory, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save memory.json: {e}")

config_manager = ConfigManager()
