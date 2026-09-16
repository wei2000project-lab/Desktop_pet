import re


_LINE_ENDING_RE = re.compile(r"\r\n?|\n")
_MANY_BLANK_LINES_RE = re.compile(r"\n{3,}")


def normalize_chat_text(text: str) -> str:
    """Keep streamed chat readable without allowing huge blank gaps."""
    if not text:
        return ""

    normalized = _LINE_ENDING_RE.sub("\n", text)
    lines = [line.rstrip() for line in normalized.split("\n")]
    normalized = "\n".join(lines)
    return _MANY_BLANK_LINES_RE.sub("\n\n", normalized)


def normalize_stream_chunk(text: str, trailing_newlines: int = 0) -> tuple[str, int]:
    normalized = normalize_chat_text(text)
    if not normalized:
        return "", trailing_newlines

    output = []
    current_trailing = trailing_newlines

    for char in normalized:
        if char == "\n":
            if current_trailing < 2:
                output.append(char)
            current_trailing += 1
        else:
            output.append(char)
            current_trailing = 0

    return "".join(output), min(current_trailing, 2)


def should_auto_scroll(value: int, maximum: int, threshold: int = 8, force: bool = False) -> bool:
    if force:
        return True
    return maximum <= 0 or value >= maximum - threshold
