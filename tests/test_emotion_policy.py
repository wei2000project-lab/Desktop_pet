from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock

from app.animation.emotion import (
    DEFAULT_EMOTION_RATE, EmotionPolicy, emotion_asset, load_emotion_rate, normalize_emotion_rate,
)
from app.contracts.emotion import Emotion, EmotionFinished, EmotionRequest
from app.core.paths import PROJECT_ROOT


class EmotionPolicyTests(unittest.TestCase):
    def test_contracts_and_policy_import_without_qt_or_services(self):
        result = subprocess.run([sys.executable, "-B", "-c", '''
import sys
from app.animation.emotion import EmotionPolicy
from app.contracts.emotion import Emotion
assert EmotionPolicy(1).choose(Emotion.SQUINT) is Emotion.SQUINT
assert not any(name == "PySide6" or name.startswith(("PySide6.", "ui.")) for name in sys.modules)
assert "app.core.config_manager" not in sys.modules
'''], cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_events_keep_the_request_identity(self):
        request = EmotionRequest(42, Emotion.SQUINT)
        self.assertEqual(request.request_id, EmotionFinished(42).request_id)
        self.assertEqual(request.emotion, Emotion.SQUINT)

    def test_rate_accepts_finite_numbers_and_ini_strings(self):
        for value, expected in ((0, 0), (1, 1), (0.3, 0.3), (" 0.75 ", 0.75)):
            with self.subTest(value=value):
                self.assertEqual(normalize_emotion_rate(value), expected)

    def test_invalid_rate_falls_back_to_default(self):
        for value in (None, "", "bad", "nan", "inf", "-inf", float("nan"),
                      -0.01, 1.01, True, False, [], {}, 10 ** 1000):
            with self.subTest(value=value):
                self.assertEqual(normalize_emotion_rate(value), DEFAULT_EMOTION_RATE)

    def test_load_uses_existing_settings_port(self):
        store = Mock()
        store.get_general.return_value = "0.8"
        self.assertEqual(load_emotion_rate(store), 0.8)
        store.get_general.assert_called_once_with("EmotionRate", 0.3)

    def test_default_config_and_user_override(self):
        from app.core.config_manager import ConfigManager, read_layered_ini
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory) / "app.ini"
            store = object.__new__(ConfigManager)
            defaults = PROJECT_ROOT / "data/config/app.defaults.ini"
            store.general_config = read_layered_ini(defaults, runtime)
            self.assertEqual(load_emotion_rate(store), 0.3)
            runtime.write_text("[General]\nemotionrate=0.9\n", encoding="utf-8")
            store.general_config = read_layered_ini(defaults, runtime)
            self.assertEqual(load_emotion_rate(store), 0.9)

    def test_endpoints_do_not_roll(self):
        roll = Mock(side_effect=AssertionError("must not roll"))
        self.assertIsNone(EmotionPolicy(0, random_value=roll).choose(Emotion.HAPPY))
        for emotion in (Emotion.HAPPY, Emotion.SURPRISED, Emotion.SQUINT):
            self.assertIs(EmotionPolicy(1, random_value=roll).choose(emotion), emotion)
        roll.assert_not_called()

    def test_probability_threshold_and_single_attempt(self):
        for value, expected in ((0, Emotion.HAPPY), (0.29999, Emotion.HAPPY),
                                (0.3, None), (0.99999, None)):
            with self.subTest(value=value):
                roll = Mock(return_value=value)
                policy = EmotionPolicy(0.3, random_value=roll)
                self.assertEqual(policy.choose("happy"), expected)
                self.assertEqual(policy.choose("squint"), expected)
                roll.assert_called_once_with()

    def test_invalid_none_and_unavailable_do_not_roll_or_retry(self):
        for emotion, available in (("none", True), ("gaze", True), ("idle", True),
                                   ("../../other.png", True), (None, True), ([], True),
                                   ("happy", False)):
            with self.subTest(emotion=emotion, available=available):
                roll = Mock(side_effect=AssertionError("must not roll"))
                policy = EmotionPolicy(0.3, random_value=roll)
                self.assertIsNone(policy.choose(emotion, asset_available=available))
                self.assertIsNone(policy.choose("happy"))
                roll.assert_not_called()

    def test_requests_have_independent_probability_decisions(self):
        roll = Mock(side_effect=(0.9, 0.1))
        first = EmotionPolicy(random_value=roll)
        second = EmotionPolicy(random_value=roll)
        self.assertIsNone(first.choose("happy"))
        self.assertEqual(second.choose("squint"), Emotion.SQUINT)
        self.assertIsNone(first.choose("happy"))
        self.assertEqual(roll.call_count, 2)

    def test_missing_asset_and_non_emotions_cannot_resolve_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertIsNone(emotion_asset("happy", directory))
            (Path(directory) / "Nova_happy.png").mkdir()
            self.assertIsNone(emotion_asset("happy", directory))
        for value in ("gaze", "idle", "none", "../Nova_idle", None, {}):
            with self.subTest(value=value):
                self.assertIsNone(emotion_asset(value))
