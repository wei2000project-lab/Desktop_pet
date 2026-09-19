import unittest
import sys
import types
from unittest.mock import Mock, patch
from tests.test_api_groups import sample_settings
from app.settings.api_group_resolver import resolve_api_request


class FakeSignal:
    def connect(self, callback):
        self.callback = callback

    def emit(self, *args, **kwargs):
        return None


class FakeQObject:
    def __init__(self, *args, **kwargs):
        pass


sys.modules.setdefault("PySide6", types.SimpleNamespace())
sys.modules.setdefault(
    "PySide6.QtCore",
    types.SimpleNamespace(
        QObject=FakeQObject,
        Signal=lambda *args, **kwargs: FakeSignal(),
        Slot=lambda *args, **kwargs: (lambda func: func),
    ),
)
sys.modules.setdefault(
    "requests",
    types.SimpleNamespace(
        Session=None,
        exceptions=types.SimpleNamespace(
            Timeout=TimeoutError,
            ConnectionError=ConnectionError,
            HTTPError=Exception,
        ),
    ),
)

import app.ai.conversation_manager as conversation_manager_module
from app.ai.conversation_manager import ConversationManager


class FakeConfigManager:
    def get_api(self, key, default=None):
        values = {
            "ApiKey": "test-key",
            "BaseUrl": "https://api.example.test/v1",
            "Model": "test-model",
            "Temperature": "0.7",
            "VerifySSL": "true",
        }
        return values.get(key, default)

    def get_active_api_key(self):
        return "test-key"

    def get_general_int(self, key, default=0):
        if key == "MaxMemoryTurns":
            return 1
        return default

    def get_general_bool(self, key, default=False):
        if key == "ConversationSummaryEnabled":
            return True
        return default

    def get_prompt(self):
        return {"system_prompt": "你是 Nova。"}

    def get_memory(self):
        return {}

    def get_history(self):
        return [
            {"role": "user", "content": "我的名字是小明"},
            {"role": "assistant", "content": "我會記得你叫小明"},
            {"role": "user", "content": "最近一輪問題"},
            {"role": "assistant", "content": "最近一輪回答"},
        ]


class FakeProvider:
    def __init__(self):
        self.request_kwargs = None

    def request(self, **kwargs):
        self.request_kwargs = kwargs


class ConversationManagerTests(unittest.TestCase):
    def test_request_messages_use_summary_and_recent_memory_limit(self):
        original_config = conversation_manager_module.config_manager
        conversation_manager_module.config_manager = FakeConfigManager()
        try:
            groups = Mock()
            groups.resolve_runtime_request.return_value = resolve_api_request(sample_settings())
            manager = ConversationManager(group_backend=groups)
            provider = FakeProvider()
            manager.provider = provider

            with patch.object(conversation_manager_module.threading, "Thread") as thread:
                thread.side_effect = lambda *, target, args, **kwargs: types.SimpleNamespace(start=lambda: target(*args))
                manager.handle_user_message("新的問題")
        finally:
            conversation_manager_module.config_manager = original_config

        messages = provider.request_kwargs["messages"]
        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("你是 Nova。", messages[0]["content"])
        self.assertIn("較早對話摘要", messages[1]["content"])
        self.assertIn("我的名字是小明", messages[1]["content"])
        self.assertEqual(messages[-3]["content"], "最近一輪問題")
        self.assertEqual(messages[-2]["content"], "最近一輪回答")
        self.assertEqual(messages[-1], {"role": "user", "content": "新的問題"})


if __name__ == "__main__":
    unittest.main()
