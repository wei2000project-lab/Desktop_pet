from typing import Any, Dict, List


Message = Dict[str, Any]


def build_conversation_context_messages(
    history: List[Message],
    max_memory_turns: int,
    summary_enabled: bool,
    summary_max_chars: int = 900,
) -> List[Message]:
    clean_history = _clean_history(history)
    recent_count = max(0, max_memory_turns) * 2
    recent_messages = clean_history[-recent_count:] if recent_count else []
    older_messages = clean_history[:-recent_count] if recent_count else clean_history

    messages: List[Message] = []
    if summary_enabled and older_messages:
        summary = summarize_conversation(older_messages, max_chars=summary_max_chars)
        if summary:
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "較早對話摘要：\n"
                        f"{summary}\n\n"
                        "請把這段摘要只當作背景脈絡，優先依照最近對話與使用者最新訊息回覆。"
                    ),
                }
            )

    messages.extend(recent_messages)
    return messages


def summarize_conversation(history: List[Message], max_chars: int = 900) -> str:
    lines = []
    for message in _clean_history(history):
        role = message["role"]
        label = "使用者" if role == "user" else "助手"
        content = _compact_text(message["content"])
        if content:
            lines.append(f"- {label}：{content}")

    summary = "\n".join(lines)
    if len(summary) <= max_chars:
        return summary
    return summary[: max(0, max_chars - 1)].rstrip() + "…"


def _clean_history(history: List[Message]) -> List[Message]:
    clean = []
    for message in history:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "").strip()
        content = str(message.get("content") or "").strip()
        if role in {"user", "assistant"} and content:
            clean.append({"role": role, "content": content})
    return clean


def _compact_text(text: str) -> str:
    return " ".join(text.split())
