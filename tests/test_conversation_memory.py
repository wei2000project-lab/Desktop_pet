import unittest

from ai.conversation_memory import build_conversation_context_messages


class ConversationMemoryTests(unittest.TestCase):
    def test_keeps_only_recent_turns_when_summary_disabled(self):
        history = [
            {"role": "user", "content": "第一輪使用者"},
            {"role": "assistant", "content": "第一輪助手"},
            {"role": "user", "content": "第二輪使用者"},
            {"role": "assistant", "content": "第二輪助手"},
            {"role": "user", "content": "第三輪使用者"},
            {"role": "assistant", "content": "第三輪助手"},
        ]

        messages = build_conversation_context_messages(
            history,
            max_memory_turns=2,
            summary_enabled=False,
        )

        self.assertEqual(
            messages,
            [
                {"role": "user", "content": "第二輪使用者"},
                {"role": "assistant", "content": "第二輪助手"},
                {"role": "user", "content": "第三輪使用者"},
                {"role": "assistant", "content": "第三輪助手"},
            ],
        )

    def test_summarizes_older_history_when_enabled(self):
        history = [
            {"role": "user", "content": "我的名字是小明"},
            {"role": "assistant", "content": "我會記得你叫小明"},
            {"role": "user", "content": "我喜歡 Edge"},
            {"role": "assistant", "content": "之後搜尋會優先考慮 Edge"},
            {"role": "user", "content": "現在幫我整理重點"},
            {"role": "assistant", "content": "可以，我來整理"},
        ]

        messages = build_conversation_context_messages(
            history,
            max_memory_turns=1,
            summary_enabled=True,
        )

        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("較早對話摘要", messages[0]["content"])
        self.assertIn("我的名字是小明", messages[0]["content"])
        self.assertIn("我喜歡 Edge", messages[0]["content"])
        self.assertEqual(
            messages[-2:],
            [
                {"role": "user", "content": "現在幫我整理重點"},
                {"role": "assistant", "content": "可以，我來整理"},
            ],
        )

    def test_zero_memory_turns_keeps_only_summary_when_enabled(self):
        history = [
            {"role": "user", "content": "舊問題"},
            {"role": "assistant", "content": "舊回答"},
        ]

        messages = build_conversation_context_messages(
            history,
            max_memory_turns=0,
            summary_enabled=True,
        )

        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("舊問題", messages[0]["content"])


if __name__ == "__main__":
    unittest.main()
