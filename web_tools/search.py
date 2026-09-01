import html
import re
from dataclasses import dataclass
from typing import List
from urllib.parse import parse_qs, unquote, urlencode, urlparse
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class WebSearchResult:
    title: str
    url: str
    snippet: str = ""


class WebSearchProvider:
    def __init__(self, timeout: float = 8.0):
        self.timeout = timeout
        self.search_url = "https://lite.duckduckgo.com/lite/"

    def search(self, query: str, limit: int = 5) -> List[WebSearchResult]:
        data = urlencode({"q": query}).encode("utf-8")
        request = Request(
            self.search_url,
            data=data,
            headers={
                "User-Agent": "Mozilla/5.0 NovaDesktopPet/1.0",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        with urlopen(request, timeout=self.timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            html_text = response.read().decode(charset, errors="replace")
        return self.parse_results(html_text, limit=limit)

    def parse_results(self, html_text: str, limit: int = 5) -> List[WebSearchResult]:
        results = self._parse_lite_results(html_text, limit)
        if results:
            return results

        return self._parse_html_results(html_text, limit)

    def _parse_html_results(self, html_text: str, limit: int) -> List[WebSearchResult]:
        blocks = re.findall(
            r'<a[^>]*class="[^"]*result__a[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>(.*?)(?=<a[^>]*class="[^"]*result__a|\Z)',
            html_text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        results: List[WebSearchResult] = []

        for raw_url, raw_title, tail in blocks:
            title = self._clean_html(raw_title)
            url = self._normalize_url(html.unescape(raw_url))
            snippet = self._extract_snippet(tail)
            if title and url and url.startswith(("http://", "https://")):
                results.append(WebSearchResult(title=title, url=url, snippet=snippet))
            if len(results) >= limit:
                break

        return results

    def _parse_lite_results(self, html_text: str, limit: int) -> List[WebSearchResult]:
        anchors = list(re.finditer(r"<a\b([^>]*)>(.*?)</a>", html_text, flags=re.IGNORECASE | re.DOTALL))
        results: List[WebSearchResult] = []

        for index, match in enumerate(anchors):
            attrs, raw_title = match.groups()
            if "result-link" not in attrs:
                continue
            raw_url = self._attr(attrs, "href")
            tail_start = match.end()
            tail_end = anchors[index + 1].start() if index + 1 < len(anchors) else len(html_text)
            tail = html_text[tail_start:tail_end]
            title = self._clean_html(raw_title)
            url = self._normalize_url(html.unescape(raw_url))
            snippet = self._extract_lite_snippet(tail)
            if title and url and url.startswith(("http://", "https://")):
                results.append(WebSearchResult(title=title, url=url, snippet=snippet))
            if len(results) >= limit:
                break

        return results

    def _extract_lite_snippet(self, result_tail: str) -> str:
        match = re.search(
            r"<td[^>]*class=['\"][^'\"]*result-snippet[^'\"]*['\"][^>]*>(.*?)</td>",
            result_tail,
            flags=re.IGNORECASE | re.DOTALL,
        )
        return self._clean_html(match.group(1)) if match else ""

    def _extract_snippet(self, result_tail: str) -> str:
        match = re.search(
            r'<a[^>]*class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>',
            result_tail,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not match:
            match = re.search(
                r'<div[^>]*class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</div>',
                result_tail,
                flags=re.IGNORECASE | re.DOTALL,
            )
        return self._clean_html(match.group(1)) if match else ""

    def _normalize_url(self, url: str) -> str:
        if url.startswith("//"):
            url = "https:" + url
        parsed = urlparse(url)
        if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
            target = parse_qs(parsed.query).get("uddg", [""])[0]
            if target:
                return unquote(target)
        return url

    @staticmethod
    def _clean_html(value: str) -> str:
        value = re.sub(r"<[^>]+>", " ", value)
        value = html.unescape(value)
        return re.sub(r"\s+", " ", value).strip()

    @staticmethod
    def _attr(attrs: str, name: str) -> str:
        match = re.search(rf"\b{name}\s*=\s*(['\"])(.*?)\1", attrs, flags=re.IGNORECASE | re.DOTALL)
        return match.group(2) if match else ""
