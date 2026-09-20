import unittest

from app.ai.errors import AIErrorCategory, AIRequestError
from app.ai.request_executor import AIRequestExecutor, RequestExecutionLimits
from app.settings.api_group_resolver import APIRequestSnapshot, ResolvedAPIKey


def request_error(*, switch=False, fallback=False, output=False):
    return AIRequestError(
        AIErrorCategory.AUTHENTICATION if switch else AIErrorCategory.INVALID_REQUEST,
        "safe test error",
        output_started=output,
        can_switch_key=switch,
        can_fallback_non_stream=fallback,
    )


def snapshot(*keys, auth_mode="api_key"):
    candidates = tuple(
        ResolvedAPIKey(f"id-{index}", f"Key {index}", index, "stored", key)
        for index, key in enumerate(keys, 1)
    )
    return APIRequestSnapshot(
        "group-id", "Group", "https://example.test/v1", "model", 0.7,
        True, auth_mode, candidates,
    )


class ScriptedFactory:
    def __init__(self, scripts):
        self.scripts = {key: list(actions) for key, actions in scripts.items()}
        self.calls = []
        self.created = []

    def __call__(self, **settings):
        client = ScriptedClient(self, settings)
        self.created.append(client)
        return client


class ScriptedClient:
    def __init__(self, factory, settings):
        self.factory = factory
        self.settings = settings
        self.cancelled = False

    def request_once(self, *_args, stream, **_kwargs):
        key = self.settings["api_key"]
        self.factory.calls.append((key, stream))
        action = self.factory.scripts[key].pop(0)
        if callable(action):
            action = action()
        if isinstance(action, Exception):
            raise action
        return action

    def cancel(self):
        self.cancelled = True


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class AIRequestExecutorTests(unittest.TestCase):
    def execute(self, snap, scripts, **executor_options):
        factory = ScriptedFactory(scripts)
        executor = AIRequestExecutor(client_factory=factory, **executor_options)
        result = executor.execute(snap, [{"role": "user", "content": "hello"}])
        return result, factory

    def test_first_candidate_success_stops_immediately(self):
        result, factory = self.execute(
            snapshot("key-1", "key-2"),
            {"key-1": ["ok"], "key-2": ["unused"]},
        )
        self.assertEqual(result, "ok")
        self.assertEqual(factory.calls, [("key-1", True)])

    def test_explicit_key_failure_uses_next_candidate_once(self):
        result, factory = self.execute(
            snapshot("key-1", "key-2"),
            {"key-1": [request_error(switch=True)], "key-2": ["ok"]},
        )
        self.assertEqual(result, "ok")
        self.assertEqual(factory.calls, [("key-1", True), ("key-2", True)])

    def test_candidate_limit_never_reaches_fourth_key(self):
        factory = ScriptedFactory({
            "key-1": [request_error(switch=True)],
            "key-2": [request_error(switch=True)],
            "key-3": [request_error(switch=True)],
            "key-4": ["must-not-run"],
        })
        executor = AIRequestExecutor(client_factory=factory)
        with self.assertRaises(AIRequestError):
            executor.execute(
                snapshot("key-1", "key-2", "key-3", "key-4"),
                [{"role": "user", "content": "hello"}],
            )
        self.assertEqual(
            factory.calls,
            [("key-1", True), ("key-2", True), ("key-3", True)],
        )

    def test_unknown_failure_does_not_switch_key(self):
        error = request_error()
        factory = ScriptedFactory({"key-1": [error], "key-2": ["unused"]})
        executor = AIRequestExecutor(client_factory=factory)
        with self.assertRaises(AIRequestError) as raised:
            executor.execute(snapshot("key-1", "key-2"), [])
        self.assertIs(raised.exception, error)
        self.assertEqual(factory.calls, [("key-1", True)])

    def test_stream_fallback_uses_same_key_once_and_stops(self):
        result, factory = self.execute(
            snapshot("key-1", "key-2"),
            {"key-1": [request_error(fallback=True), "ok"], "key-2": ["unused"]},
        )
        self.assertEqual(result, "ok")
        self.assertEqual(factory.calls, [("key-1", True), ("key-1", False)])

    def test_failed_non_stream_fallback_does_not_then_switch_key(self):
        final_error = request_error(switch=True)
        factory = ScriptedFactory({
            "key-1": [request_error(fallback=True), final_error],
            "key-2": ["unused"],
        })
        executor = AIRequestExecutor(client_factory=factory)
        with self.assertRaises(AIRequestError) as raised:
            executor.execute(snapshot("key-1", "key-2"), [])
        self.assertIs(raised.exception, final_error)
        self.assertEqual(factory.calls, [("key-1", True), ("key-1", False)])

    def test_partial_output_never_falls_back_or_switches(self):
        error = request_error(switch=True, fallback=True, output=True)
        factory = ScriptedFactory({"key-1": [error], "key-2": ["unused"]})
        executor = AIRequestExecutor(client_factory=factory)
        with self.assertRaises(AIRequestError) as raised:
            executor.execute(snapshot("key-1", "key-2"), [])
        self.assertIs(raised.exception, error)
        self.assertEqual(factory.calls, [("key-1", True)])

    def test_cancellation_after_failure_prevents_next_candidate(self):
        cancelled = False

        def cancel_then_fail():
            nonlocal cancelled
            cancelled = True
            return request_error(switch=True)

        factory = ScriptedFactory({
            "key-1": [cancel_then_fail],
            "key-2": ["unused"],
        })
        executor = AIRequestExecutor(client_factory=factory)
        with self.assertRaises(AIRequestError) as raised:
            executor.execute(
                snapshot("key-1", "key-2"), [], should_cancel=lambda: cancelled,
            )
        self.assertEqual(raised.exception.category, AIErrorCategory.CANCELLED)
        self.assertEqual(factory.calls, [("key-1", True)])

    def test_operation_deadline_prevents_next_candidate(self):
        clock = FakeClock()

        def expire_then_fail():
            clock.now = 6.0
            return request_error(switch=True)

        factory = ScriptedFactory({
            "key-1": [expire_then_fail],
            "key-2": ["unused"],
        })
        executor = AIRequestExecutor(
            client_factory=factory,
            clock=clock,
            limits=RequestExecutionLimits(operation_timeout=5.0),
        )
        with self.assertRaises(AIRequestError) as raised:
            executor.execute(snapshot("key-1", "key-2"), [])
        self.assertEqual(raised.exception.category, AIErrorCategory.OPERATION_TIMEOUT)
        self.assertEqual(factory.calls, [("key-1", True)])
        self.assertLessEqual(factory.created[0].settings["timeout"], 5.0)

    def test_http_budget_blocks_fallback_request(self):
        factory = ScriptedFactory({"key-1": [request_error(fallback=True)]})
        executor = AIRequestExecutor(
            client_factory=factory,
            limits=RequestExecutionLimits(max_http_attempts=1),
        )
        with self.assertRaises(AIRequestError) as raised:
            executor.execute(snapshot("key-1"), [])
        self.assertEqual(raised.exception.category, AIErrorCategory.BUDGET_EXHAUSTED)
        self.assertEqual(factory.calls, [("key-1", True)])

    def test_none_auth_mode_makes_one_credential_free_attempt(self):
        result, factory = self.execute(
            snapshot(auth_mode="none"),
            {None: ["ok"]},
        )
        self.assertEqual(result, "ok")
        self.assertEqual(factory.calls, [(None, True)])


if __name__ == "__main__":
    unittest.main()
