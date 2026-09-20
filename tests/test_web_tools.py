import unittest
from unittest.mock import Mock

from app.web.context import WebContextBuilder
from app.web.decision import WebSearchDecision, WebSearchDecider
from app.web.extractor import WebPageExtractor
from app.web.search import WebSearchProvider
from app.web.search import WebSearchResult
from app.web.service import WebToolService
from app.settings.api_group_resolver import resolve_api_request
from tests.test_api_groups import sample_settings


class WebToolsTests(unittest.TestCase):
    def test_search_parser_extracts_duckduckgo_results(self):
        html = """
        <html><body>
          <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fnews">Example News</a>
          <a class="result__snippet">Short snippet about the news.</a>
        </body></html>
        """

        results = WebSearchProvider().parse_results(html, limit=5)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].title, "Example News")
        self.assertEqual(results[0].url, "https://example.com/news")
        self.assertEqual(results[0].snippet, "Short snippet about the news.")

    def test_search_parser_extracts_duckduckgo_lite_post_results(self):
        html = """
        <html><body>
          <tr>
            <td>1.&nbsp;</td>
            <td><a rel="nofollow" href="https://openai.com/news/" class='result-link'>OpenAI News</a></td>
          </tr>
          <tr>
            <td>&nbsp;&nbsp;&nbsp;</td>
            <td class='result-snippet'>Stay up to speed on AI news.</td>
          </tr>
        </body></html>
        """

        results = WebSearchProvider().parse_results(html, limit=5)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].title, "OpenAI News")
        self.assertEqual(results[0].url, "https://openai.com/news/")
        self.assertEqual(results[0].snippet, "Stay up to speed on AI news.")

    def test_extractor_removes_page_chrome_and_keeps_main_text(self):
        html = """
        <html><body>
          <nav>menu links should disappear</nav>
          <main>
            <h1>Useful title</h1>
            <p>This is the article body with important information.</p>
            <script>tracking()</script>
          </main>
          <footer>footer should disappear</footer>
        </body></html>
        """

        text = WebPageExtractor().extract_text(html)

        self.assertIn("Useful title", text)
        self.assertIn("important information", text)
        self.assertNotIn("menu links", text)
        self.assertNotIn("footer should disappear", text)
        self.assertNotIn("tracking", text)

    def test_extractor_keeps_text_after_sidebar_container(self):
        html = """
        <main>
          <p>Article introduction before the sidebar.</p>
          <div class="sidebar">Related links should disappear.</div>
          <p>Article conclusion after the sidebar.</p>
        </main>
        """

        text = WebPageExtractor().extract_text(html)

        self.assertIn("Article introduction before the sidebar.", text)
        self.assertIn("Article conclusion after the sidebar.", text)
        self.assertNotIn("Related links should disappear.", text)

    def test_extractor_skips_nested_content_until_noise_container_ends(self):
        html = """
        <main>
          <div id="advert-panel">
            Advertisement text should disappear.
            <div><p>Nested promotion should also disappear.</p></div>
          </div>
          <p>Useful article content remains available.</p>
        </main>
        """

        text = WebPageExtractor().extract_text(html)

        self.assertIn("Useful article content remains available.", text)
        self.assertNotIn("Advertisement text should disappear.", text)
        self.assertNotIn("Nested promotion should also disappear.", text)

    def test_extractor_handles_multiple_noise_containers(self):
        html = """
        <main>
          <div class="cookie-banner">Cookie notice should disappear.</div>
          <aside><p>Aside content should disappear.</p></aside>
          <section class="promo"><p>Promotion should disappear.</p></section>
          <p>Final article paragraph should remain.</p>
        </main>
        """

        text = WebPageExtractor().extract_text(html)

        self.assertEqual(text, "Final article paragraph should remain.")

    def test_context_builder_limits_items_and_summarizes(self):
        records = [
            {
                "title": f"Title {idx}",
                "url": f"https://example{idx}.com/article",
                "snippet": "snippet",
                "text": "第一句有重點。第二句補充細節。第三句不應該全部塞進去。",
            }
            for idx in range(6)
        ]

        context = WebContextBuilder(max_results=5).build(records)

        self.assertIn("網路查詢摘要", context)
        self.assertIn("Title 0", context)
        self.assertIn("example0.com", context)
        self.assertNotIn("Title 5", context)
        self.assertLessEqual(context.count("來源"), 5)

    def test_decider_uses_keyword_gate_and_parses_json(self):
        decider = WebSearchDecider()

        self.assertFalse(decider.needs_decision("你好，今天心情很好"))
        self.assertTrue(decider.needs_decision("幫我查最新 Python 版本"))

        decision = decider.parse_decision('{"should_search": true, "query": "Python latest version", "reason": "最新資訊"}')

        self.assertEqual(
            decision,
            WebSearchDecision(should_search=True, query="Python latest version", reason="最新資訊"),
        )

    def test_service_skips_search_when_message_does_not_need_web(self):
        class SearchProvider:
            called = False

            def search(self, query, limit=5):
                self.called = True
                return []

        search_provider = SearchProvider()
        service = WebToolService(search_provider=search_provider)

        context = service.build_context_if_needed(
            "你好，隨便聊聊", resolve_api_request(sample_settings())
        )

        self.assertEqual(context, "")
        self.assertFalse(search_provider.called)

    def test_service_keeps_partial_results_when_one_page_fails(self):
        class SearchProvider:
            def search(self, query, limit=5):
                return [
                    WebSearchResult("Good Page", "https://example.com/good", "good snippet"),
                    WebSearchResult("Bad Page", "https://example.com/bad", "bad snippet"),
                ]

        class Extractor:
            def fetch_text(self, url):
                if "bad" in url:
                    raise RuntimeError("boom")
                return "正文第一句有重點。正文第二句補充。"

        executor_factory = Mock()
        executor_factory.return_value.execute.return_value = (
            '{"should_search": true, "query": "最新測試資料", "reason": "最新資訊"}'
        )
        service = WebToolService(
            search_provider=SearchProvider(),
            extractor=Extractor(),
            executor_factory=executor_factory,
        )

        context = service.build_context_if_needed(
            "幫我查最新測試資料", resolve_api_request(sample_settings())
        )

        self.assertIn("網路查詢摘要", context)
        self.assertIn("Good Page", context)
        self.assertIn("Bad Page", context)
        self.assertIn("bad snippet", context)

    def test_service_does_not_search_after_decision_is_cancelled(self):
        search_provider = Mock()
        executor_factory = Mock()
        executor_factory.return_value.execute.return_value = (
            '{"should_search": true, "query": "最新測試資料", "reason": "最新資訊"}'
        )
        service = WebToolService(
            search_provider=search_provider,
            executor_factory=executor_factory,
        )
        cancelled = Mock(side_effect=(False, True))

        context = service.build_context_if_needed(
            "幫我查最新測試資料",
            resolve_api_request(sample_settings()),
            should_cancel=cancelled,
        )

        self.assertEqual(context, "")
        search_provider.search.assert_not_called()


if __name__ == "__main__":
    unittest.main()
