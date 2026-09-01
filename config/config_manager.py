import os
import configparser
import json
from typing import Any, Dict, List
from ai.api_keys import decode_api_key_entries, encode_api_key_entries, first_api_key
from utils.logger import logger

class ConfigManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConfigManager, cls).__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        self.config_dir = os.path.dirname(os.path.abspath(__file__))
        self.root_dir = os.path.dirname(self.config_dir)
        
        self.config_ini_path = os.path.join(self.config_dir, "config.ini")
        self.api_ini_path = os.path.join(self.config_dir, "api.ini")
        self.prompt_json_path = os.path.join(self.config_dir, "prompt.json")
        self.history_json_path = os.path.join(self.config_dir, "history.json")
        self.memory_json_path = os.path.join(self.config_dir, "memory.json")
        self.env_path = os.path.join(self.root_dir, ".env")

        self.general_config = configparser.ConfigParser()
        self.api_config = configparser.ConfigParser()

        self.load_env()
        self.load_configs()

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
        if os.path.exists(self.config_ini_path):
            self.general_config.read(self.config_ini_path, encoding="utf-8")
        else:
            logger.warning("config.ini not found, using empty config")
            self.general_config.add_section("General")

        # API Config
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
        try:
            raw_entries = self.api_config.get("API", "ApiKeys")
        except (configparser.NoSectionError, configparser.NoOptionError):
            raw_entries = ""
        return decode_api_key_entries(raw_entries, legacy_key=self.get_api("ApiKey", ""))

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
            with open(self.api_ini_path, "w", encoding="utf-8") as f:
                self.api_config.write(f)
        except Exception as e:
            logger.error(f"Failed to save api.ini: {e}")

    # JSON Handlers (Prompt, History, Memory)
    def get_prompt(self) -> Dict[str, Any]:
        if os.path.exists(self.prompt_json_path):
            try:
                with open(self.prompt_json_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load prompt.json: {e}")
        return {}

    def save_prompt(self, prompt_data: Dict[str, Any]):
        try:
            with open(self.prompt_json_path, "w", encoding="utf-8") as f:
                json.dump(prompt_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save prompt.json: {e}")

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
            with open(self.memory_json_path, "w", encoding="utf-8") as f:
                json.dump(memory, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save memory.json: {e}")

config_manager = ConfigManager()
