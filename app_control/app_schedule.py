import re
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable


@dataclass(frozen=True)
class ScheduleDelay:
    seconds: int
    label: str
    run_at: datetime


class AppOpenScheduler:
    def schedule(self, delay_seconds: int, callback: Callable[[], None]) -> None:
        timer = threading.Timer(delay_seconds, callback)
        timer.daemon = True
        timer.start()


def parse_schedule_delay(user_text: str, now: datetime | None = None) -> ScheduleDelay | None:
    text = user_text.strip()
    current_time = now or datetime.now()

    patterns = (
        (r"(\d+)\s*秒\s*後", 1, "秒"),
        (r"(\d+)\s*分鐘\s*後", 60, "分鐘"),
        (r"(\d+)\s*分\s*鐘?\s*後", 60, "分鐘"),
        (r"(\d+)\s*小時\s*後", 3600, "小時"),
    )
    for pattern, multiplier, unit_label in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        amount = int(match.group(1))
        if amount <= 0:
            return None
        seconds = amount * multiplier
        return ScheduleDelay(
            seconds=seconds,
            label=f"{amount} {unit_label}後",
            run_at=current_time + timedelta(seconds=seconds),
        )

    absolute_match = re.search(r"(?<!\d)([01]?\d|2[0-3])\s*[:：]\s*([0-5]\d)(?!\d)", text)
    if absolute_match:
        hour = int(absolute_match.group(1))
        minute = int(absolute_match.group(2))
        run_at = current_time.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if run_at <= current_time:
            return None
        seconds = int((run_at - current_time).total_seconds())
        return ScheduleDelay(
            seconds=seconds,
            label=f"{hour:02d}:{minute:02d}",
            run_at=run_at,
        )

    return None
