import re
from typing import Dict, Iterable, List
from urllib.parse import urlparse


class WebContextBuilder:
    def __init__(self, max_results: int = 5, summary_chars: int = 180, total_chars: int = 1200):
        self.max_results = max_results
        self.summary_chars = summary_chars
        self.total_chars = total_chars

    def build(self, records: Iterable[Dict[str, str]]) -> str:
        lines: List[str] = [
            "網路查詢摘要：以下資料已先移除網頁導覽、廣告與頁尾，並壓縮成短摘要；請只把它當作當輪回答的參考。"
        ]

        count = 0
        for record in records:
            if count >= self.max_results:
                break
            title = self._compact(record.get("title", ""), 80)
            url = record.get("url", "")
            domain = self._domain(url)
            summary = self.summarize(record.get("text") or record.get("snippet") or "")
            if not title or not summary:
                continue
            count += 1
            lines.append(f"{count}. {title}\n來源：{domain}\n摘要：{summary}")

        if count == 0:
            return ""

        context = "\n\n".join(lines)
        return context[: self.total_chars].strip()

    def summarize(self, text: str) -> str:
        text = self._normalize_text(text)
        if not text:
            return ""

        sentences = [part.strip() for part in re.split(r"(?<=[。！？.!?])\s+|\n+", text) if part.strip()]
        if not sentences:
            return self._compact(text, self.summary_chars)

        selected = " ".join(sentences[:2])
        return self._compact(selected, self.summary_chars)

    def _compact(self, text: str, limit: int) -> str:
        text = self._normalize_text(text)
        if len(text) <= limit:
            return text
        return text[: max(0, limit - 1)].rstrip() + "…"

    @staticmethod
    def _normalize_text(text: str) -> str:
        return re.sub(r"\s+", " ", text or "").strip()

    @staticmethod
    def _domain(url: str) -> str:
        domain = urlparse(url).netloc
        return domain.replace("www.", "") if domain else url
