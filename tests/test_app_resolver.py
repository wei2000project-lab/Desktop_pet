import unittest

from app_control.app_aliases import AppAliasConfig, GenericAlias
from app_control.app_index import AppEntry
from app_control.app_resolver import AppResolveError, resolve_app_from_text, resolve_app_name


class AppResolverTests(unittest.TestCase):
    def test_resolves_generic_search_tool_to_available_browser(self):
        result = resolve_app_from_text(
            "幫我開啟查詢工具",
            [
                AppEntry(name="Google Chrome", path="C:/Chrome.lnk"),
                AppEntry(name="Microsoft Word", path="C:/Word.lnk"),
            ],
        )

        self.assertEqual(result.app_name, "Google Chrome")
        self.assertEqual(result.error, "")

    def test_rejects_mentioned_uninstalled_app_instead_of_fallback(self):
        result = resolve_app_from_text(
            "幫我開啟 discord",
            [
                AppEntry(name="Google Chrome", path="C:/Chrome.lnk"),
                AppEntry(name="Microsoft Word", path="C:/Word.lnk"),
            ],
        )

        self.assertEqual(result.error, AppResolveError.REQUESTED_APP_NOT_INSTALLED)
        self.assertEqual(result.requested_name, "discord")
        self.assertEqual(result.app_name, "")

    def test_resolves_ai_selected_alias_to_canonical_index_name(self):
        result = resolve_app_name(
            "chrome",
            [
                AppEntry(name="Google Chrome", path="C:/Chrome.lnk"),
                AppEntry(name="Microsoft Word", path="C:/Word.lnk"),
            ],
        )

        self.assertEqual(result.app_name, "Google Chrome")
        self.assertEqual(result.error, "")

    def test_resolves_custom_configured_alias_without_code_change(self):
        aliases = AppAliasConfig(
            generic_aliases=(
                GenericAlias(
                    key="chat",
                    triggers=("聊天工具",),
                    candidates=("Discord",),
                    reason="使用者需要聊天工具",
                ),
            ),
            app_aliases={"dc": ("Discord",)},
        )

        generic_result = resolve_app_from_text(
            "幫我開聊天工具",
            [AppEntry(name="Discord", path="C:/Discord.lnk")],
            aliases=aliases,
        )
        app_result = resolve_app_name(
            "dc",
            [AppEntry(name="Discord", path="C:/Discord.lnk")],
            aliases=aliases,
        )

        self.assertEqual(generic_result.app_name, "Discord")
        self.assertEqual(app_result.app_name, "Discord")

    def test_generic_alias_with_multiple_installed_candidates_requests_choice(self):
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

        result = resolve_app_from_text(
            "幫我開瀏覽工具",
            [
                AppEntry(name="Google Chrome", path="C:/Chrome.lnk"),
                AppEntry(name="Microsoft Edge", path="C:/Edge.lnk"),
            ],
            aliases=aliases,
        )

        self.assertEqual(result.error, AppResolveError.APP_CHOICE_REQUIRED)
        self.assertEqual(result.preference_key, "browser")
        self.assertEqual(result.choices, ("Google Chrome", "Microsoft Edge"))

    def test_generic_alias_prefers_saved_choice_when_available(self):
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

        result = resolve_app_from_text(
            "幫我開瀏覽工具",
            [
                AppEntry(name="Google Chrome", path="C:/Chrome.lnk"),
                AppEntry(name="Microsoft Edge", path="C:/Edge.lnk"),
            ],
            aliases=aliases,
            preferences={"browser": "Microsoft Edge"},
        )

        self.assertEqual(result.app_name, "Microsoft Edge")
        self.assertEqual(result.error, "")


if __name__ == "__main__":
    unittest.main()
