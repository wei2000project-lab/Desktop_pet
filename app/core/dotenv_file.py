"""Small, local .env reader and update renderer for API key variables."""
import re
from pathlib import Path
from typing import Mapping


_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_ASSIGNMENT = re.compile(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*=([^\r\n]*)(\r?\n)?\Z")


class DotEnvFile:
    def __init__(self, path: Path | str):
        self.path = Path(path)

    def _text(self) -> str:
        if not self.path.exists():
            return ""
        with self.path.open("r", encoding="utf-8-sig", newline="") as file:
            return file.read()

    def read_values(self) -> dict[str, str]:
        values = {}
        for line in self._text().splitlines(keepends=True):
            match = _ASSIGNMENT.fullmatch(line)
            if match:
                values[match.group(1)] = match.group(2).strip()
        return values

    def render_updates(
        self, updates: Mapping[str, str | None], *, owned_existing: set[str] | frozenset[str] = frozenset(),
    ) -> str:
        for name, value in updates.items():
            if type(name) is not str or not _NAME.fullmatch(name) or (
                value is not None and (not isinstance(value, str) or "\n" in value or "\r" in value)
            ):
                raise ValueError("環境變數名稱或金鑰格式無效。")

        original = self._text()
        lines = original.splitlines(keepends=True)
        found = set()
        result = []
        for line in lines:
            match = _ASSIGNMENT.fullmatch(line)
            if not match or match.group(1) not in updates:
                result.append(line)
                continue
            name = match.group(1)
            if name in found or name not in owned_existing:
                raise ValueError("環境變數名稱衝突；原檔未修改。")
            found.add(name)
            value = updates[name]
            if value is not None:
                result.append(f"{name}={value}{match.group(3) or ''}")

        newline = "\r\n" if "\r\n" in original else "\n"
        for name, value in updates.items():
            if name in found or value is None:
                continue
            if result and not result[-1].endswith(("\n", "\r")):
                result.append(newline)
            result.append(f"{name}={value}{newline}")
        return "".join(result)
