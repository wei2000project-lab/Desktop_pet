import unittest

from app.ai.emotion_response import (
    EMOTION_PREFIX, MAX_HEADER_CHARS, EmotionResponseParser, parse_emotion_response,
)
from app.contracts.emotion import Emotion


class EmotionResponseTests(unittest.TestCase):
    def test_header_diagnostics_distinguish_none_missing_and_invalid_without_body(self):
        for raw, status in (
            ("[[emotion:none]]\nprivate body", "valid"),
            ("private body", "missing"),
            ("[[emotion:private-name]]\nprivate body", "invalid_name"),
            ("[[emotion:happy\nprivate body", "malformed"),
            (EMOTION_PREFIX + "x" * MAX_HEADER_CHARS, "too_long"),
            ("[[emotion:hap", "truncated"),
        ):
            for split in range(len(raw) + 1):
                parser = EmotionResponseParser()
                parser.feed(raw[:split])
                parser.feed(raw[split:])
                parser.finish()
                self.assertEqual(parser.header_status, status)
                self.assertNotIn("private", parser.header_status)

    def assert_parse(self, source, emotion, body):
        whole = parse_emotion_response(source)
        self.assertEqual((whole.emotion, whole.text), (emotion, body))
        # Exercise every two-chunk split as well as one-character network chunks.
        partitions = [[source[:split], source[split:]] for split in range(len(source) + 1)]
        partitions.append(list(source))
        for chunks in partitions:
            with self.subTest(chunks=chunks):
                parser = EmotionResponseParser()
                output = []
                for chunk in chunks:
                    output.append(parser.feed(chunk))
                    self.assertLessEqual(parser.buffered_chars, MAX_HEADER_CHARS)
                output.append(parser.finish())
                self.assertEqual("".join(output), body)
                self.assertEqual(parser.emotion, emotion)
                self.assertEqual(parser.buffered_chars, 0)
                self.assertEqual(parser.finish(), "")
                self.assertEqual(parser.feed("late data"), "")

    def test_all_choices_and_line_endings(self):
        for emotion in Emotion:
            for separator in ("", "\n", "\r\n"):
                self.assert_parse(f"[[emotion:{emotion.value}]]{separator}你好！",
                                  emotion, "你好！")

    def test_body_whitespace_markdown_and_quotes_are_preserved(self):
        body = "  說明\n\n```text\n[[emotion:squint]]\n```\n"
        self.assert_parse("[[emotion:happy]]\n" + body, Emotion.HAPPY, body)
        self.assert_parse("[[emotion:none]]\n\n下一段", Emotion.NONE, "\n下一段")
        self.assert_parse("[[emotion:happy]]\rX", Emotion.HAPPY, "\rX")
        self.assert_parse("[[emotion:happy]]\r", Emotion.HAPPY, "\r")

    def test_unmarked_and_similar_text_is_unchanged(self):
        for text in ("", "你好", "\n你好\n", "[", "[[", "[[emot", "[[emotion", "[[example]]",
                     "提到 [[emotion:happy]] 的文字", " [[emotion:happy]]\n原文"):
            self.assert_parse(text, Emotion.NONE, text)

    def test_invalid_names_are_removed_without_a_candidate(self):
        for name in ("idle", "gaze", "unknown", "", " happy ", "HAPPY", "../happy.png"):
            self.assert_parse(f"[[emotion:{name}]]\n仍然回答", Emotion.NONE, "仍然回答")

    def test_truncated_and_malformed_control_prefixes(self):
        for text in (EMOTION_PREFIX, "[[emotion:happy", "[[emotion:happy]"):
            self.assert_parse(text, Emotion.NONE, "")
        for newline in ("\n", "\r\n"):
            self.assert_parse("[[emotion:bad" + newline + "正文", Emotion.NONE, "正文")

    def test_overlong_header_has_a_fixed_discard_boundary(self):
        header = EMOTION_PREFIX + "x" * (MAX_HEADER_CHARS - len(EMOTION_PREFIX))
        self.assert_parse(header + "正文繼續", Emotion.NONE, "正文繼續")
        parser = EmotionResponseParser()
        text = header + "x" * 100000
        self.assertEqual(parser.feed(text), "x" * 100000)
        self.assertEqual(parser.buffered_chars, 0)

    def test_emotion_is_ready_before_body_and_cannot_be_changed(self):
        parser = EmotionResponseParser()
        self.assertEqual(parser.feed("[[emotion:sur"), "")
        self.assertIsNone(parser.emotion)
        self.assertEqual(parser.feed("prised]]"), "")
        self.assertEqual(parser.emotion, Emotion.SURPRISED)
        self.assertEqual(parser.feed("\n[[emotion:happy]]正文"), "[[emotion:happy]]正文")
        self.assertEqual(parser.emotion, Emotion.SURPRISED)

    def test_interleaved_requests_do_not_share_prefix_state(self):
        first, second = EmotionResponseParser(), EmotionResponseParser()
        self.assertEqual(first.feed("[[emotion:sq"), "")
        self.assertEqual(second.feed("正常回答"), "正常回答")
        self.assertEqual(first.feed("uint]]\n懷疑"), "懷疑")
        self.assertEqual(first.emotion, Emotion.SQUINT)
        self.assertEqual(second.emotion, Emotion.NONE)
