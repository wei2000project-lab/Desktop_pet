from typing import Callable, Dict, List

from app.utils.logger import logger
from web_tools.context import WebContextBuilder
from web_tools.decision import WebSearchDecider
from web_tools.extractor import WebPageExtractor
from web_tools.search import WebSearchProvider


class WebToolService:
    def __init__(
        self,
        search_provider: WebSearchProvider = None,
        extractor: WebPageExtractor = None,
        context_builder: WebContextBuilder = None,
        decider: WebSearchDecider = None,
    ):
        self.search_provider = search_provider or WebSearchProvider()
        self.extractor = extractor or WebPageExtractor()
        self.context_builder = context_builder or WebContextBuilder(max_results=5)
        self.decider = decider or WebSearchDecider()

    def build_context_if_needed(
        self,
        user_text: str,
        api_url: str,
        api_key: str,
        model: str,
        verify_ssl: bool,
        should_cancel: Callable[[], bool] = None,
    ) -> str:
        if not self.decider.needs_decision(user_text):
            return ""
        if self._cancelled(should_cancel):
            return ""

        decision = self._decide(user_text, api_url, api_key, model, verify_ssl, should_cancel)
        if not decision.should_search or not decision.query:
            return ""

        logger.info(f"Web tool searching | query={decision.query} | reason={decision.reason}")
        try:
            results = self.search_provider.search(decision.query, limit=5)
        except Exception as exc:
            logger.warning(f"Web search failed: {exc}")
            return self._failure_context()

        records: List[Dict[str, str]] = []
        for result in results[:5]:
            if self._cancelled(should_cancel):
                return ""
            text = ""
            if len(records) < 3:
                try:
                    text = self.extractor.fetch_text(result.url)
                except Exception as exc:
                    logger.warning(f"Web page extraction failed for {result.url}: {exc}")
            records.append(
                {
                    "title": result.title,
                    "url": result.url,
                    "snippet": result.snippet,
                    "text": text,
                }
            )

        context = self.context_builder.build(records)
        return context or self._failure_context()

    def _decide(self, user_text: str, api_url: str, api_key: str, model: str, verify_ssl: bool, should_cancel):
        if not api_key:
            return self.decider.fallback_decision(user_text)
        try:
            from ai.client import AIClient

            client = AIClient(api_url, api_key, model, verify_ssl=verify_ssl, timeout=20.0)
            raw = client.request_completion(
                messages=self.decider.build_decision_messages(user_text),
                temperature=0.0,
                max_chars=120,
                on_chunk_cb=None,
                should_cancel=should_cancel,
            )
            return self.decider.parse_decision(raw)
        except Exception as exc:
            logger.warning(f"Web decision failed, falling back to keyword query: {exc}")
            return self.decider.fallback_decision(user_text)

    @staticmethod
    def _cancelled(should_cancel) -> bool:
        return bool(should_cancel and should_cancel())

    @staticmethod
    def _failure_context() -> str:
        return "網路查詢摘要：本輪判斷需要網路資料，但目前無法取得可用的搜尋結果；回答時請明確說明資料有限。"
