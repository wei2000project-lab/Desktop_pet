import pathlib
import unittest


class ConversationWebContextSourceTests(unittest.TestCase):
    def test_conversation_manager_builds_web_context_before_request(self):
        source = pathlib.Path("app/ai/conversation_manager.py").read_text(encoding="utf-8")

        self.assertIn("WebToolService", source)
        self.assertIn("self.web_tool.build_context_if_needed", source)
        self.assertIn("網路查詢摘要", source)
        self.assertIn("messages.append({\"role\": \"system\", \"content\": web_context})", source)

    def test_web_context_is_not_saved_to_history(self):
        source = pathlib.Path("app/ai/conversation_manager.py").read_text(encoding="utf-8")

        self.assertIn("history.append({\"role\": \"user\", \"content\": user_text})", source)
        self.assertIn("history.append({\"role\": \"assistant\", \"content\": full_response})", source)
        self.assertNotIn("history.append(web_context", source)


if __name__ == "__main__":
    unittest.main()
