import unittest

from ui.message_formatting import (
    normalize_chat_text,
    normalize_stream_chunk,
    should_auto_scroll,
)


class MessageFormattingTests(unittest.TestCase):
    def test_normalize_chat_text_limits_blank_lines_and_trims_line_endings(self):
        text = "第一行   \r\n\r\n\r\n\r\n第二行\t\n\n\n第三行"

        self.assertEqual(normalize_chat_text(text), "第一行\n\n第二行\n\n第三行")

    def test_normalize_chat_text_preserves_single_line_streaming_chunks(self):
        self.assertEqual(normalize_chat_text("你好，世界"), "你好，世界")

    def test_normalize_stream_chunk_limits_blank_lines_across_chunk_boundaries(self):
        first, trailing_newlines = normalize_stream_chunk("第一行\n\n", 0)
        second, trailing_newlines = normalize_stream_chunk("\n\n第二行", trailing_newlines)

        self.assertEqual(first + second, "第一行\n\n第二行")
        self.assertEqual(trailing_newlines, 0)

    def test_should_auto_scroll_when_already_near_bottom(self):
        self.assertTrue(should_auto_scroll(value=94, maximum=100))

    def test_should_not_auto_scroll_when_user_is_reading_history(self):
        self.assertFalse(should_auto_scroll(value=20, maximum=100))

    def test_should_auto_scroll_when_forced(self):
        self.assertTrue(should_auto_scroll(value=20, maximum=100, force=True))


if __name__ == "__main__":
    unittest.main()
