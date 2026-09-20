import unittest
from unittest.mock import Mock
import requests

from app.ai.client import AIClient
import app.ai.client as client_module
from app.ai.errors import (
    AIErrorCategory, AIRequestError, classify_http_response, internal_error,
)
from app.settings.connection_test import safe_failure_message


class FakeResponse:
    def __init__(self, status, payload=None):
        self.status_code = status
        self._payload = payload

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class AIErrorTests(unittest.TestCase):
    def test_only_explicit_key_error_code_allows_key_switch(self):
        error = classify_http_response(FakeResponse(401, {
            "error": {"code": "invalid_api_key", "message": "secret-key-value"},
        }))
        self.assertEqual(error.category, AIErrorCategory.AUTHENTICATION)
        self.assertEqual(error.http_status, 401)
        self.assertEqual(error.service_code, "invalid_api_key")
        self.assertTrue(error.can_switch_key)
        self.assertNotIn("secret-key-value", str(error))
        self.assertNotIn("secret-key-value", repr(error))

        generic = classify_http_response(FakeResponse(401, {
            "error": {"message": "secret-key-value"},
        }))
        self.assertFalse(generic.can_switch_key)

    def test_rate_limit_and_quota_are_not_key_switch_conditions(self):
        rate_limit = classify_http_response(FakeResponse(429, {
            "error": {"code": "rate_limit_exceeded"},
        }))
        quota = classify_http_response(FakeResponse(429, {
            "error": {"code": "insufficient_quota"},
        }))
        self.assertEqual(rate_limit.category, AIErrorCategory.RATE_LIMIT)
        self.assertEqual(quota.category, AIErrorCategory.QUOTA)
        self.assertFalse(rate_limit.can_switch_key)
        self.assertFalse(quota.can_switch_key)

    def test_stream_fallback_requires_explicit_code_and_no_output(self):
        unsupported = FakeResponse(400, {
            "error": {"code": "streaming_not_supported"},
        })
        self.assertTrue(classify_http_response(unsupported).can_fallback_non_stream)
        self.assertFalse(
            classify_http_response(unsupported, output_started=True).can_fallback_non_stream
        )
        self.assertFalse(
            classify_http_response(FakeResponse(400, {"error": {"code": "bad_request"}}))
            .can_fallback_non_stream
        )

    def test_untrusted_service_code_is_not_retained(self):
        error = classify_http_response(FakeResponse(500, {
            "error": {"code": "invalid api key: secret-value"},
        }))
        self.assertIsNone(error.service_code)
        self.assertEqual(error.category, AIErrorCategory.SERVER)
        self.assertNotIn("secret-value", repr(error))

    def test_transport_and_http_exceptions_become_safe_categories(self):
        cases = (
            (requests.exceptions.Timeout("secret-timeout"), AIErrorCategory.TIMEOUT),
            (requests.exceptions.ConnectionError("secret-host"), AIErrorCategory.CONNECTION),
            (requests.exceptions.SSLError("secret-certificate"), AIErrorCategory.TLS),
            (ValueError("secret-json"), AIErrorCategory.INVALID_RESPONSE),
            (RuntimeError("secret-internal"), AIErrorCategory.INTERNAL),
        )
        for source, category in cases:
            with self.subTest(category=category):
                error = AIClient._structured_error(source)
                self.assertEqual(error.category, category)
                self.assertNotIn("secret", str(error))
                self.assertNotIn("secret", repr(error))

        response = FakeResponse(401, {
            "error": {"code": "invalid_api_key", "message": "secret-body"},
        })
        source = requests.exceptions.HTTPError("secret-http", response=response)
        error = AIClient._structured_error(source)
        self.assertEqual(error.category, AIErrorCategory.AUTHENTICATION)
        self.assertTrue(error.can_switch_key)
        self.assertNotIn("secret", str(error))

    def test_request_once_never_performs_hidden_stream_fallback(self):
        client = AIClient("https://example.test/v1", "fake-key", "model")
        error = AIRequestError(
            AIErrorCategory.INVALID_REQUEST,
            "API 不支援串流。",
            http_status=400,
            service_code="streaming_not_supported",
            can_fallback_non_stream=True,
        )
        client._request_stream = Mock(side_effect=error)
        client._request_non_stream = Mock(return_value="ok")
        with self.assertRaises(AIRequestError) as raised:
            client.request_once(
                [{"role": "user", "content": "hi"}], stream=True,
            )
        self.assertIs(raised.exception, error)
        client._request_non_stream.assert_not_called()

    def test_request_once_propagates_arbitrary_or_partial_failure(self):
        for error in (
            internal_error(),
            AIRequestError(
                AIErrorCategory.INVALID_REQUEST,
                "API 不支援串流。",
                output_started=True,
                can_fallback_non_stream=True,
            ),
        ):
            with self.subTest(category=error.category, output_started=error.output_started):
                client = AIClient("https://example.test/v1", "fake-key", "model")
                client._request_stream = Mock(side_effect=error)
                client._request_non_stream = Mock(return_value="should-not-run")
                with self.assertRaises(AIRequestError) as raised:
                    client.request_once(
                        [{"role": "user", "content": "hi"}], stream=True,
                    )
                self.assertIs(raised.exception, error)
                client._request_non_stream.assert_not_called()

    def test_connection_test_uses_category_without_forwarding_error_text(self):
        error = AIRequestError(
            AIErrorCategory.PERMISSION,
            "private upstream message secret-value",
            http_status=403,
        )
        message = safe_failure_message(error)
        self.assertEqual(message, "存取遭拒，請確認帳號、模型與權限。")
        self.assertNotIn("secret-value", message)

    def test_non_stream_http_failure_is_classified_without_body(self):
        class Response(FakeResponse):
            def raise_for_status(self):
                raise client_module.requests.exceptions.HTTPError(
                    "secret-http-message", response=self,
                )

        class Session:
            def post(self, *_args, **_kwargs):
                return Response(401, {
                    "error": {"code": "invalid_api_key", "message": "secret-body"},
                })

            def close(self):
                pass

        original = client_module.requests.Session
        client_module.requests.Session = Session
        try:
            client = AIClient("https://example.test/v1", "fake-key", "model")
            with self.assertRaises(AIRequestError) as raised:
                client.test_connection()
        finally:
            client_module.requests.Session = original
        self.assertEqual(raised.exception.category, AIErrorCategory.AUTHENTICATION)
        self.assertTrue(raised.exception.can_switch_key)
        self.assertNotIn("secret", str(raised.exception))

    def test_visible_stream_content_prevents_retry_after_callback_failure(self):
        class Response(FakeResponse):
            def raise_for_status(self):
                pass

            def iter_lines(self):
                yield b'data: {"choices":[{"delta":{"content":"visible"}}]}'

        class Session:
            def post(self, *_args, **_kwargs):
                return Response(200, {})

            def close(self):
                pass

        original = client_module.requests.Session
        client_module.requests.Session = Session
        try:
            client = AIClient("https://example.test/v1", "fake-key", "model")
            with self.assertRaises(AIRequestError) as raised:
                client.request_once(
                    [{"role": "user", "content": "hi"}],
                    on_chunk_cb=Mock(side_effect=RuntimeError("secret-callback")),
                    stream=True,
                )
        finally:
            client_module.requests.Session = original
        self.assertTrue(raised.exception.output_started)
        self.assertFalse(raised.exception.can_switch_key)
        self.assertFalse(raised.exception.can_fallback_non_stream)
        self.assertNotIn("secret", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
