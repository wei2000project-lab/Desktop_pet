from dataclasses import dataclass


LOW_CONFIDENCE_THRESHOLD = 0.70
HIGH_CONFIDENCE_THRESHOLD = 0.90


@dataclass(frozen=True)
class ConfidenceDecision:
    action: str

    @property
    def should_open(self) -> bool:
        return self.action == "open"

    @property
    def should_confirm(self) -> bool:
        return self.action == "confirm"

    @property
    def should_rephrase(self) -> bool:
        return self.action == "rephrase"


def decide_app_open_action(confidence: float, confirm_before_open: bool) -> ConfidenceDecision:
    if confidence < LOW_CONFIDENCE_THRESHOLD:
        return ConfidenceDecision("rephrase")
    if confidence < HIGH_CONFIDENCE_THRESHOLD:
        return ConfidenceDecision("confirm")
    if confirm_before_open:
        return ConfidenceDecision("confirm")
    return ConfidenceDecision("open")
