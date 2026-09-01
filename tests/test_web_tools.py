import unittest

from web_tools.context import WebContextBuilder
from web_tools.decision import WebSearchDecision, WebSearchDecider
from web_tools.extractor import WebPageExtractor
from web_tools.search import WebSearchProvider
from web_tools.search import WebSearchResult
from web_tools.service import WebToolService


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

        context = service.build_context_if_needed("你好，隨便聊聊", "", "", "", True)

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

        service = WebToolService(search_provider=SearchProvider(), extractor=Extractor())

        context = service.build_context_if_needed("幫我查最新測試資料", "", "", "", True)

        self.assertIn("網路查詢摘要", context)
        self.assertIn("Good Page", context)
        self.assertIn("Bad Page", context)
        self.assertIn("bad snippet", context)


if __name__ == "__main__":
    unittest.main()
