import unittest

from app.ai.prompt_builder import build_system_prompt


class PromptBuilderTests(unittest.TestCase):
    def test_emotion_protocol_is_opt_in_until_conversation_parser_is_wired(self):
        prompt = build_system_prompt({"system_prompt": "你是 Nova。"})
        self.assertNotIn("[[emotion:", prompt)

    def test_emotion_protocol_preserves_custom_personality(self):
        prompt = build_system_prompt({
            "system_prompt": "你是 Nova。", "selected_personality": "custom",
            "custom_personality": "使用繁體中文。",
        }, emotion_enabled=True)
        self.assertIn("你是 Nova。", prompt)
        self.assertIn("完整人格設定：\n使用繁體中文。", prompt)
        self.assertEqual(prompt.count("回覆表情協定："), 1)
        for name in ("happy", "surprised", "squint", "none"):
            self.assertIn(name, prompt)
        self.assertIn("懷疑、半信半疑", prompt)
        self.assertIn("不要只因使用者提到情緒字詞", prompt)
        self.assertIn("不自行抽機率", prompt)

    def test_emotion_protocol_distinguishes_quoted_tasks_from_nova_reactions(self):
        prompt = build_system_prompt({}, emotion_enabled=True)
        self.assertIn("純翻譯、改寫、摘要、分類、排序或程式碼輸出應選 none", prompt)
        self.assertIn("情緒屬於引文角色，不是 Nova 的反應", prompt)
        self.assertIn("說法不可信、誇大、矛盾或需要查證，選 squint", prompt)

    def test_build_system_prompt_does_not_add_reply_length_instruction(self):
        prompt = build_system_prompt(
            {"system_prompt": "你是 Nova。"},
            max_chars=120,
        )

        self.assertIn("你是 Nova。", prompt)
        self.assertNotIn("回答長度規則", prompt)
        self.assertNotIn("請將每次回答控制", prompt)

    def test_build_system_prompt_adds_one_complete_personality_prompt(self):
        prompt = build_system_prompt(
            {
                "system_prompt": "你是 Nova。",
                "selected_personality": "catgirl_companion",
            },
            max_chars=80,
        )

        self.assertIn("完整人格設定：", prompt)
        self.assertIn("你是 Nova，一位女生貓娘桌寵", prompt)
        self.assertNotIn("簡潔直答型", prompt)

    def test_build_system_prompt_uses_custom_personality_as_exclusive_profile(self):
        prompt = build_system_prompt(
            {
                "system_prompt": "你是 Nova。",
                "selected_personality": "custom",
                "custom_personality": "使用繁體中文，稱呼使用者為球球。",
            },
            max_chars=80,
        )

        self.assertIn("使用繁體中文，稱呼使用者為球球。", prompt)

    def test_build_system_prompt_ignores_custom_personality_when_not_selected(self):
        prompt = build_system_prompt(
            {
                "system_prompt": "你是 Nova。",
                "selected_personality": "warm_companion",
                "custom_personality": "不要加入這段。",
            },
            max_chars=80,
        )

        self.assertNotIn("不要加入這段。", prompt)

    def test_build_system_prompt_migrates_legacy_multi_select_to_first_profile(self):
        prompt = build_system_prompt(
            {
                "system_prompt": "你是 Nova。",
                "personality_options": ["concise", "cute"],
            },
            max_chars=80,
        )

        self.assertIn("簡潔直答型", prompt)
        self.assertNotIn("可愛陪伴型", prompt)


if __name__ == "__main__":
    unittest.main()
