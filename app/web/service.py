from dataclasses import replace
from typing import Callable, Dict, List

from app.ai.request_executor import AIRequestExecutor, RequestExecutionLimits
from app.settings.api_group_resolver import APIRequestSnapshot
from app.utils.logger import logger
from app.web.context import WebContextBuilder
from app.web.decision import WebSearchDecider
from app.web.extractor import WebPageExtractor
from app.web.search import WebSearchProvider


class WebToolService:
    def __init__(
        self,
        search_provider: WebSearchProvider = None,
        extractor: WebPageExtractor = None,
        context_builder: WebContextBuilder = None,
        decider: WebSearchDecider = None,
        executor_factory=AIRequestExecutor,
    ):
        self.search_provider = search_provider or WebSearchProvider()
        self.extractor = extractor or WebPageExtractor()
        self.context_builder = context_builder or WebContextBuilder(max_results=5)
        self.decider = decider or WebSearchDecider()
        self.executor_factory = executor_factory

    def build_context_if_needed(
        self,
        user_text: str,
        snapshot: APIRequestSnapshot,
        should_cancel: Callable[[], bool] = None,
    ) -> str:
        if not self.decider.needs_decision(user_text):
            return ""
        if self._cancelled(should_cancel):
            return ""

        decision = self._decide(user_text, snapshot, should_cancel)
        if self._cancelled(should_cancel):
            return ""
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

    def _decide(self, user_text: str, snapshot: APIRequestSnapshot, should_cancel):
        try:
            executor = self.executor_factory(
                limits=RequestExecutionLimits(operation_timeout=20.0)
            )
            decision_snapshot = replace(snapshot, temperature=0.0)
            raw = executor.execute(
                decision_snapshot,
                self.decider.build_decision_messages(user_text),
                max_chars=120,
                on_chunk_cb=None,
                should_cancel=should_cancel,
            )
            return self.decider.parse_decision(raw)
        except Exception:
            logger.warning("Web decision failed; using keyword fallback.")
            return self.decider.fallback_decision(user_text)

    @staticmethod
    def _cancelled(should_cancel) -> bool:
        return bool(should_cancel and should_cancel())

    @staticmethod
    def _failure_context() -> str:
        return "網路查詢摘要：本輪判斷需要網路資料，但目前無法取得可用的搜尋結果；回答時請明確說明資料有限。"
