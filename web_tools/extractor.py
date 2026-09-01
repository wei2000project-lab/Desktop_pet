import html
import re
from html.parser import HTMLParser
from typing import List
from urllib.request import Request, urlopen


class _ReadableTextParser(HTMLParser):
    SKIP_TAGS = {
        "script",
        "style",
        "noscript",
        "svg",
        "nav",
        "header",
        "footer",
        "aside",
        "form",
        "button",
    }
    BLOCK_TAGS = {"p", "div", "article", "section", "main", "br", "li", "h1", "h2", "h3"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._parts: List[str] = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        attrs_dict = {name.lower(): value or "" for name, value in attrs}
        if tag in self.SKIP_TAGS or self._is_ad_like(attrs_dict):
            self._skip_depth += 1
            return
        if tag in self.BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag):
        tag = tag.lower()
        if self._skip_depth and tag in self.SKIP_TAGS:
            self._skip_depth -= 1
            return
        if not self._skip_depth and tag in self.BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data):
        if self._skip_depth:
            return
        text = data.strip()
        if text:
            self._parts.append(text)

    def text(self) -> str:
        raw = " ".join(self._parts)
        raw = html.unescape(raw)
        raw = re.sub(r"[ \t\r\f\v]+", " ", raw)
        raw = re.sub(r"\n\s*\n+", "\n", raw)
        raw = re.sub(r" ?\n ?", "\n", raw)
        return raw.strip()

    @staticmethod
    def _is_ad_like(attrs) -> bool:
        marker = " ".join([attrs.get("class", ""), attrs.get("id", ""), attrs.get("role", "")]).lower()
        ad_words = ("advert", "ads", "banner", "cookie", "subscribe", "promo", "sidebar")
        return any(word in marker for word in ad_words)


class WebPageExtractor:
    def __init__(self, timeout: float = 8.0, max_chars: int = 8000):
        self.timeout = timeout
        self.max_chars = max_chars

    def fetch_text(self, url: str) -> str:
        request = Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 NovaDesktopPet/1.0"},
        )
        with urlopen(request, timeout=self.timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            html_text = response.read().decode(charset, errors="replace")
        return self.extract_text(html_text)

    def extract_text(self, html_text: str) -> str:
        parser = _ReadableTextParser()
        parser.feed(html_text)
        text = parser.text()
        lines = [line.strip() for line in text.splitlines() if self._keep_line(line)]
        compact = "\n".join(lines)
        return compact[: self.max_chars].strip()

    @staticmethod
    def _keep_line(line: str) -> bool:
        line = line.strip()
        if len(line) < 8:
            return False
        lowered = line.lower()
        noisy = ("privacy policy", "terms of use", "all rights reserved", "cookie")
        return not any(word in lowered for word in noisy)
