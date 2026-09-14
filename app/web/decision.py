import json
import re
from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class WebSearchDecision:
    should_search: bool
    query: str
    reason: str = ""


class WebSearchDecider:
    KEYWORDS = (
        "查詢",
        "搜尋",
        "上網",
        "最新",
        "新聞",
        "價格",
        "版本",
        "規格",
        "資料",
        "recent",
        "latest",
        "search",
        "news",
        "price",
    )
    TEMPORAL_WORDS = ("今天", "現在", "目前", "即時", "recent", "current")
    INFO_WORDS = ("查", "搜尋", "新聞", "價格", "版本", "規格", "資料", "多少", "是什麼")

    def needs_decision(self, user_text: str) -> bool:
        text = user_text.strip().lower()
        if not text:
            return False
        if any(keyword.lower() in text for keyword in self.KEYWORDS):
            return True
        return any(word.lower() in text for word in self.TEMPORAL_WORDS) and any(
            word.lower() in text for word in self.INFO_WORDS
        )

    def build_decision_messages(self, user_text: str) -> List[dict]:
        return [
            {
                "role": "system",
                "content": (
                    "你是網路查詢工具選擇器。只回傳 JSON，不要加說明。"
                    "格式：{\"should_search\": true/false, \"query\": \"短搜尋字串\", \"reason\": \"短原因\"}。"
                    "只有問題需要最新、即時、外部資料或明確要求搜尋時才 should_search=true。"
                ),
            },
            {"role": "user", "content": user_text[:300]},
        ]

    def parse_decision(self, raw_text: str) -> WebSearchDecision:
        data = self._load_json(raw_text)
        should_search = bool(data.get("should_search", False))
        query = str(data.get("query", "")).strip()
        reason = str(data.get("reason", "")).strip()
        return WebSearchDecision(should_search=should_search, query=query, reason=reason)

    def fallback_decision(self, user_text: str) -> WebSearchDecision:
        if not self.needs_decision(user_text):
            return WebSearchDecision(False, "", "")
        return WebSearchDecision(True, self._clean_query(user_text), "keyword_gate")

    def _load_json(self, raw_text: str) -> dict:
        raw_text = (raw_text or "").strip()
        try:
            return json.loads(raw_text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", raw_text, flags=re.DOTALL)
            if match:
                return json.loads(match.group(0))
            raise

    @staticmethod
    def _clean_query(user_text: str) -> str:
        query = re.sub(r"^(幫我|請|可以|能不能|麻煩你)?(查詢|搜尋|查|找|上網查)?", "", user_text.strip())
        return query.strip()[:120] or user_text.strip()[:120]
