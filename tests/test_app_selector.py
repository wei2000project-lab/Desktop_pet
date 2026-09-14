import unittest

from app.control.resolution.aliases import AppAliasConfig, GenericAlias
from app.control.discovery.index import AppEntry
from app.control.preferences import AppPreferenceStore
from app.control.resolution.resolver import resolve_preference_change_from_text
from app.control.resolution.selector import AppSelection, AppSelector, parse_app_selection


class AppSelectorTests(unittest.TestCase):
    def test_parse_valid_json_selection(self):
        selection = parse_app_selection(
            '{"action":"open_app","app_name":"Google Chrome","confidence":0.95,"reason":"使用者想上網"}'
        )

        self.assertEqual(
            selection,
            AppSelection(
                action="open_app",
                app_name="Google Chrome",
                confidence=0.95,
                reason="使用者想上網",
                error="",
            ),
        )

    def test_parse_json_inside_markdown_fence(self):
        selection = parse_app_selection(
            '```json\n{"action":"open_app","app_name":"Word","confidence":0.8,"reason":"寫報告"}\n```'
        )

        self.assertEqual(selection.app_name, "Word")
        self.assertEqual(selection.action, "open_app")

    def test_parse_invalid_json_returns_error_selection(self):
        selection = parse_app_selection("我覺得應該開 Chrome")

        self.assertEqual(selection.action, "none")
        self.assertEqual(selection.error, "invalid_json")

    def test_selector_sends_only_app_names_not_paths(self):
        captured_messages = []

        def fake_complete(messages):
            captured_messages.extend(messages)
            return '{"action":"open_app","app_name":"Google Chrome","confidence":0.95,"reason":"上網"}'

        selector = AppSelector(fake_complete)
        selection = selector.select_app(
            "幫我開啟適合工作的工具",
            [
                AppEntry(name="Google Chrome", path="C:/secret/Chrome.lnk"),
                AppEntry(name="Word", path="C:/secret/Word.lnk"),
            ],
        )

        sent_text = "\n".join(message["content"] for message in captured_messages)
        self.assertTrue(selection.success)
        self.assertEqual(selection.app_name, "Google Chrome")
        self.assertIn("Google Chrome", sent_text)
        self.assertIn("Word", sent_text)
        self.assertNotIn("C:/secret", sent_text)

    def test_selector_rejects_app_name_not_in_list(self):
        selector = AppSelector(
            lambda messages: '{"action":"open_app","app_name":"cmd.exe","confidence":0.99,"reason":"bad"}'
        )

        selection = selector.select_app("開系統工具", [AppEntry(name="Word", path="C:/Word.lnk")])

        self.assertFalse(selection.success)
        self.assertEqual(selection.error, "app_not_in_index")
        self.assertEqual(selection.app_name, "cmd.exe")

    def test_selector_rejects_low_confidence_ai_selection(self):
        selector = AppSelector(
            lambda messages: '{"action":"open_app","app_name":"Google Chrome","confidence":0.61,"reason":"不確定"}'
        )

        selection = selector.select_app(
            "幫我開那個查東西的",
            [AppEntry(name="Google Chrome", path="C:/Chrome.lnk")],
        )

        self.assertFalse(selection.success)
        self.assertEqual(selection.error, "low_confidence")
        self.assertEqual(selection.app_name, "Google Chrome")

    def test_selector_rejects_uninstalled_requested_app_without_ai_fallback(self):
        def fake_complete(messages):
            return '{"action":"open_app","app_name":"Google Chrome","confidence":0.95,"reason":"fallback"}'

        selector = AppSelector(fake_complete)
        selection = selector.select_app(
            "幫我開啟 Discord",
            [AppEntry(name="Google Chrome", path="C:/Chrome.lnk")],
        )

        self.assertFalse(selection.success)
        self.assertEqual(selection.error, "requested_app_not_installed")
        self.assertEqual(selection.app_name, "discord")

    def test_selector_uses_injected_alias_config_before_ai(self):
        called = []
        aliases = AppAliasConfig(
            generic_aliases=(
                GenericAlias(
                    key="chat",
                    triggers=("聊天工具",),
                    candidates=("Discord",),
                    reason="使用者需要聊天工具",
                ),
            ),
            app_aliases={},
        )

        def fake_complete(messages):
            called.append(messages)
            return '{"action":"open_app","app_name":"Google Chrome","confidence":0.95,"reason":"fallback"}'

        selector = AppSelector(fake_complete, aliases=aliases)
        selection = selector.select_app(
            "幫我開聊天工具",
            [
                AppEntry(name="Discord", path="C:/Discord.lnk"),
                AppEntry(name="Google Chrome", path="C:/Chrome.lnk"),
            ],
        )

        self.assertTrue(selection.success)
        self.assertEqual(selection.app_name, "Discord")
        self.assertEqual(selection.confidence, 1.0)
        self.assertEqual(called, [])

    def test_selector_resolves_cmd_alias_locally_before_ai(self):
        called = []

        def fake_complete(messages):
            called.append(messages)
            return "不是 JSON"

        selector = AppSelector(fake_complete)
        selection = selector.select_app(
            "幫我在9:45開啟cmd",
            [
                AppEntry(name="Command Prompt", path="C:/Command Prompt.lnk"),
                AppEntry(name="Google Chrome", path="C:/Chrome.lnk"),
            ],
        )

        self.assertTrue(selection.success)
        self.assertEqual(selection.app_name, "Command Prompt")
        self.assertEqual(called, [])


    def test_selector_requests_user_choice_when_alias_has_multiple_available_apps(self):
        aliases = AppAliasConfig(
            generic_aliases=(
                GenericAlias(
                    key="browser",
                    triggers=("瀏覽工具",),
                    candidates=("Google Chrome", "Microsoft Edge"),
                    reason="使用者需要瀏覽工具",
                ),
            ),
            app_aliases={},
        )

        selector = AppSelector(lambda messages: "", aliases=aliases)
        selection = selector.select_app(
            "幫我開瀏覽工具",
            [
                AppEntry(name="Google Chrome", path="C:/Chrome.lnk"),
                AppEntry(name="Microsoft Edge", path="C:/Edge.lnk"),
            ],
        )

        self.assertFalse(selection.success)
        self.assertEqual(selection.error, "app_choice_required")
        self.assertEqual(selection.preference_key, "browser")
        self.assertEqual(selection.choices, ("Google Chrome", "Microsoft Edge"))

    def test_selector_uses_saved_preference_for_alias_category(self):
        class FakePreferenceStore:
            def load_preferences(self):
                return {"browser": "Microsoft Edge"}

        aliases = AppAliasConfig(
            generic_aliases=(
                GenericAlias(
                    key="browser",
                    triggers=("瀏覽工具",),
                    candidates=("Google Chrome", "Microsoft Edge"),
                    reason="使用者需要瀏覽工具",
                ),
            ),
            app_aliases={},
        )

        selector = AppSelector(lambda messages: "", aliases=aliases, preference_store=FakePreferenceStore())
        selection = selector.select_app(
            "幫我開瀏覽工具",
            [
                AppEntry(name="Google Chrome", path="C:/Chrome.lnk"),
                AppEntry(name="Microsoft Edge", path="C:/Edge.lnk"),
            ],
        )

        self.assertTrue(selection.success)
        self.assertEqual(selection.app_name, "Microsoft Edge")

    def test_preference_change_resolver_requests_choice_for_matching_category(self):
        aliases = AppAliasConfig(
            generic_aliases=(
                GenericAlias(
                    key="browser",
                    triggers=("搜尋", "瀏覽工具"),
                    candidates=("Google Chrome", "Microsoft Edge"),
                    reason="使用者需要查詢或上網工具",
                ),
            ),
            app_aliases={},
        )

        selection = resolve_preference_change_from_text(
            "更改搜尋偏好",
            [
                AppEntry(name="Google Chrome", path="C:/Chrome.lnk"),
                AppEntry(name="Microsoft Edge", path="C:/Edge.lnk"),
            ],
            aliases=aliases,
        )

        self.assertFalse(selection.success)
        self.assertEqual(selection.error, "app_choice_required")
        self.assertEqual(selection.preference_key, "browser")
        self.assertEqual(selection.choices, ("Google Chrome", "Microsoft Edge"))

    def test_preference_change_resolver_reports_missing_candidates(self):
        aliases = AppAliasConfig(
            generic_aliases=(
                GenericAlias(
                    key="browser",
                    triggers=("搜尋",),
                    candidates=("Google Chrome", "Microsoft Edge"),
                    reason="使用者需要查詢或上網工具",
                ),
            ),
            app_aliases={},
        )

        selection = resolve_preference_change_from_text(
            "更改搜尋偏好",
            [AppEntry(name="Word", path="C:/Word.lnk")],
            aliases=aliases,
        )

        self.assertFalse(selection.success)
        self.assertEqual(selection.error, "requested_app_not_installed")
        self.assertEqual(selection.preference_key, "browser")


if __name__ == "__main__":
    unittest.main()
