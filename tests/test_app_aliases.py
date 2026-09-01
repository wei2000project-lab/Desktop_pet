import json
import tempfile
import unittest
from pathlib import Path

from app_control.app_aliases import AppAliasConfig, load_app_alias_config


class AppAliasConfigTests(unittest.TestCase):
    def test_loads_alias_groups_from_json_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            alias_path = Path(tmp) / "app_aliases.json"
            alias_path.write_text(
                json.dumps(
                    {
                        "generic_aliases": [
                            {
                                "key": "chat",
                                "triggers": ["聊天工具"],
                                "candidates": ["Discord"],
                                "reason": "使用者需要聊天工具",
                            }
                        ],
                        "app_aliases": {
                            "dc": ["Discord"],
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            config = load_app_alias_config(alias_path)

        self.assertEqual(config.generic_aliases[0].triggers, ("聊天工具",))
        self.assertEqual(config.generic_aliases[0].candidates, ("Discord",))
        self.assertEqual(config.generic_aliases[0].key, "chat")
        self.assertEqual(config.app_aliases["dc"], ("Discord",))

    def test_invalid_or_missing_config_falls_back_to_defaults(self):
        config = load_app_alias_config(Path("missing-app-aliases.json"))

        self.assertIsInstance(config, AppAliasConfig)
        self.assertIn("chrome", config.app_aliases)


if __name__ == "__main__":
    unittest.main()
