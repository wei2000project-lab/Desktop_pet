import unittest
import sys
import types

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
from ai.client import AIClient
import ai.client as client_module


class AIClientPayloadTests(unittest.TestCase):
    def test_openai_compatible_payload_omits_nonstandard_thinking_field(self):
        client = AIClient(
            base_url="https://api.groq.com/openai/v1",
            api_key="test-key",
            model="llama-3.1-8b-instant",
        )

        payload = client._build_payload(
            messages=[{"role": "user", "content": "hello"}],
            temperature=0.7,
            max_chars=100,
            stream=True,
        )

        self.assertNotIn("thinking", payload)
        self.assertNotIn("max_tokens", payload)
        self.assertEqual(payload["model"], "llama-3.1-8b-instant")
        self.assertTrue(payload["stream"])

    def test_non_stream_response_is_not_hard_truncated_by_max_chars(self):
        long_content = "這是一段超過限制但不應該被程式硬切掉的完整回答。"

        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {"choices": [{"message": {"content": long_content}}]}

        class FakeSession:
            def post(self, *args, **kwargs):
                return FakeResponse()

            def close(self):
                return None

        original_session = client_module.requests.Session
        client_module.requests.Session = lambda: FakeSession()
        try:
            client = AIClient(
                base_url="https://api.groq.com/openai/v1",
                api_key="test-key",
                model="llama-3.1-8b-instant",
            )

            result = client._request_non_stream(
                messages=[{"role": "user", "content": "hello"}],
                temperature=0.7,
                max_chars=5,
                on_chunk_cb=None,
            )
        finally:
            client_module.requests.Session = original_session

        self.assertEqual(result, long_content)

    def test_connection_probe_uses_non_stream_minimal_request(self):
        captured = {}

        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {"choices": [{"message": {"content": "ok"}}]}

        class FakeSession:
            def post(self, *args, **kwargs):
                captured["json"] = kwargs["json"]
                return FakeResponse()

            def close(self):
                return None

        original_session = client_module.requests.Session
        client_module.requests.Session = lambda: FakeSession()
        try:
            client = AIClient(
                base_url="https://api.groq.com/openai/v1",
                api_key="test-key",
                model="llama-3.1-8b-instant",
            )

            self.assertTrue(client.test_connection())
        finally:
            client_module.requests.Session = original_session

        self.assertFalse(captured["json"]["stream"])
        self.assertEqual(captured["json"]["messages"][-1]["content"], "ping")


if __name__ == "__main__":
    unittest.main()
