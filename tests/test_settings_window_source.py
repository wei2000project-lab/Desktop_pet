import pathlib
import unittest


class SettingsWindowSourceTests(unittest.TestCase):
    def test_ai_settings_no_longer_exposes_system_prompt_editor(self):
        source = pathlib.Path("ui/settings_window.py").read_text(encoding="utf-8")

        self.assertNotIn("system_prompt_input", source)
        self.assertNotIn("System Prompt:", source)
        self.assertNotIn('prompt_data["system_prompt"]', source)

    def test_ai_settings_exposes_memory_controls(self):
        source = pathlib.Path("ui/settings_window.py").read_text(encoding="utf-8")

        self.assertIn("最大記憶輪數", source)
        self.assertIn("歷史紀錄上限", source)
        self.assertIn("啟用過去對話摘要", source)
        self.assertIn("MaxMemoryTurns", source)
        self.assertIn("HistoryLimit", source)
        self.assertIn("ConversationSummaryEnabled", source)
        self.assertNotIn("輸出文字最大數量", source)
        self.assertNotIn("max_chars_input", source)
        self.assertNotIn('set_api("MaxChars"', source)

    def test_ai_settings_exposes_multiple_api_key_controls(self):
        source = pathlib.Path("ui/settings_window.py").read_text(encoding="utf-8")

        self.assertIn("api_key_rows", source)
        self.assertIn("add_api_key_row", source)
        self.assertIn("測試連線", source)
        self.assertIn("set_api_key_entries", source)

    def test_api_key_rows_use_full_width_and_red_trash_delete_button(self):
        source = pathlib.Path("ui/settings_window.py").read_text(encoding="utf-8")

        self.assertIn('api_keys_label = QLabel("API Keys:")', source)
        self.assertIn("ai_layout.addRow(api_keys_label)", source)
        self.assertIn("ai_layout.addRow(self.api_keys_container)", source)
        self.assertNotIn('ai_layout.addRow(QLabel("API Keys:"), self.api_keys_container)', source)
        self.assertIn('QPushButton("🗑")', source)
        self.assertIn("#b3261e", source)
        self.assertIn("test_btn.setFixedWidth(64)", source)
        self.assertIn("name_input.setFixedWidth(48)", source)

    def test_pet_settings_exposes_reading_idle_seconds(self):
        source = pathlib.Path("ui/settings_window.py").read_text(encoding="utf-8")

        self.assertIn("reading_idle_seconds_input", source)
        self.assertIn("ReadingIdleSeconds", source)
        self.assertIn("進入閱讀狀態閒置秒數", source)


if __name__ == "__main__":
    unittest.main()
