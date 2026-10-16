from typing import Any, Dict, List


EMOTION_INSTRUCTION = (
    "回覆表情協定：依對話語境與你準備回答的內容，選擇 Nova 回覆時的表情。"
    "happy 表示開心、稱讚或慶祝；surprised 表示驚訝或意外；"
    "squint 表示懷疑、半信半疑；沒有合適表情時選 none。"
    "不要只因使用者提到情緒字詞、引用或否定句就選該表情，也不要在嚴肅安慰時錯配開心表情。"
    "每則回覆必須從 [[emotion:名稱]] 開始，接一個換行再寫正常正文；"
    "名稱只可為 happy、surprised、squint、none，不能使用 idle 或 gaze。"
    "只輸出一次標記，不加前置空白或程式碼圍欄，不在正文重複控制標記。"
    "不要輸出檔案路徑或任意動作指令。只判斷是否適合，不自行抽機率；程式會決定是否顯示。"
)


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


def build_system_prompt(prompt_data: Dict[str, Any], max_chars: int = 0, *, emotion_enabled=False) -> str:
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

    # Enable only when the conversation caller also strips the control prefix.
    if emotion_enabled:
        sections.append(EMOTION_INSTRUCTION)

    return "\n\n".join(section for section in sections if section)
