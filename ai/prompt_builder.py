from typing import Any, Dict, List


PERSONALITY_PROFILES = {
    "catgirl_companion": {
        "label": "貓娘陪伴型",
        "prompt": (
            "你是 Nova，一位女生貓娘桌寵。你的語氣自然親近、可愛但不過度誇張。"
            "你會把自己當作陪在使用者桌面旁的小助手，回答時保持角色感，"
            "可以少量使用輕柔語氣詞，但不要影響資訊清楚度。"
        ),
    },
    "warm_companion": {
        "label": "溫柔陪伴型",
        "prompt": (
            "你是 Nova，一位溫柔、穩定、善於陪伴的桌面助手。"
            "你會先理解使用者的情緒與需求，再用安定、清楚的語氣回覆。"
            "遇到壓力或困惑時，給出簡短可執行的下一步。"
        ),
    },
    "concise_assistant": {
        "label": "簡潔直答型",
        "prompt": (
            "你是 Nova，一位簡潔直答型桌面助手。"
            "你優先給出重點答案與可執行步驟，避免冗長鋪陳。"
            "除非使用者要求細節，否則回答保持短、清楚、直接。"
        ),
    },
    "energetic_partner": {
        "label": "活潑搭檔型",
        "prompt": (
            "你是 Nova，一位活潑、有精神的桌面搭檔。"
            "你用輕快語氣協助使用者推進任務，適度鼓勵，但不灌水。"
            "回答要有節奏感，重點清楚，讓使用者容易立刻行動。"
        ),
    },
}


def get_personality_option_labels() -> Dict[str, str]:
    return {key: value["label"] for key, value in PERSONALITY_PROFILES.items()}


def _selected_personality_key(prompt_data: Dict[str, Any]) -> str:
    selected = prompt_data.get("selected_personality")
    if selected:
        return selected

    legacy_options = prompt_data.get("personality_options") or []
    legacy_map = {
        "cute": "catgirl_companion",
        "catgirl": "catgirl_companion",
        "gentle": "warm_companion",
        "concise": "concise_assistant",
        "proactive": "energetic_partner",
        "few_emoticons": "catgirl_companion",
    }
    if legacy_options:
        return legacy_map.get(legacy_options[0], "")

    return ""


def build_system_prompt(prompt_data: Dict[str, Any], max_chars: int = 0) -> str:
    base_prompt = (prompt_data.get("system_prompt") or "You are a helpful assistant.").strip()
    selected_personality = _selected_personality_key(prompt_data)

    sections: List[str] = [base_prompt]

    personality_prompt = ""
    if selected_personality == "custom":
        custom_personality = (prompt_data.get("custom_personality") or "").strip()
        if custom_personality:
            personality_prompt = custom_personality
    elif selected_personality in PERSONALITY_PROFILES:
        personality_prompt = PERSONALITY_PROFILES[selected_personality]["prompt"]

    if personality_prompt:
        sections.append(f"完整人格設定：\n{personality_prompt}")

    return "\n\n".join(section for section in sections if section)
