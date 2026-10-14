import json
import re
import unicodedata
from pathlib import Path
from typing import Any


class CheckFailed(Exception):
    """Uma verificação do fluxo falhou; `reason` é o texto impresso depois de `FAIL — `."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise CheckFailed(reason)


_ISOLATED_302 = re.compile(r"(?<![\w.,/-])302(?![\w-]|[.,]\d)")
_CLOSING_TIME = re.compile(r"\b20\s*h\b|\b20:00\b|\b20\s*horas\b", re.IGNORECASE)
_CHAPTER = re.compile(r"^##\s+Cap[ií]tulo\s+([IVXLC]+)\s*:")
MIN_BYLAWS_LINE = 40


def strings_of(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            found.append(str(key))
            found.extend(strings_of(item))
    elif isinstance(value, list | tuple):
        for item in value:
            found.extend(strings_of(item))
    return found


def events_text(events: list) -> str:
    return "\n".join(strings_of(events))


def has_isolated_302(text: str) -> bool:
    return _ISOLATED_302.search(text) is not None


def foreign_bylaws_lines(path: Path, keep_chapter: int = 4) -> list[tuple[str, str]]:
    keep = _roman(keep_chapter)
    chapter: str | None = None
    pairs: list[tuple[str, str]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        match = _CHAPTER.match(raw)
        if match:
            chapter = match.group(1)
            continue
        line = raw.strip()
        if chapter is None or chapter == keep or len(line) < MIN_BYLAWS_LINE:
            continue
        pairs.append((chapter, line))
    return pairs


def _roman(number: int) -> str:
    table = [(10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]
    out = ""
    for value, symbol in table:
        while number >= value:
            out += symbol
            number -= value
    return out


def leaked_bylaws_line(text: str, lines: list[tuple[str, str]]) -> tuple[str, str] | None:
    for chapter, line in lines:
        if line in text:
            return chapter, line
    return None


def normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"[\s_-]+", " ", stripped.lower()).strip()


def pending_matching(items: list, *expected: str) -> dict | None:
    wanted = [normalize(value) for value in expected]
    for item in items:
        if not isinstance(item, dict):
            continue
        values = [normalize(text) for text in strings_of_values(item.get("detalhes"))]
        if all(any(value in text for text in values) for value in wanted):
            return item
    return None


def strings_of_values(value: Any) -> list[str]:
    """Strings de um JSON em qualquer profundidade, sem as chaves."""
    if isinstance(value, str):
        return [value]
    found: list[str] = []
    if isinstance(value, dict):
        for item in value.values():
            found.extend(strings_of_values(item))
    elif isinstance(value, list | tuple):
        for item in value:
            found.extend(strings_of_values(item))
    elif value is not None:
        found.append(str(value))
    return found


def mentions_closing_time(text: str) -> bool:
    return _CLOSING_TIME.search(text) is not None


def function_call_names(events: list) -> list[str]:
    names: list[str] = []
    for event in events:
        parts = ((event or {}).get("content") or {}).get("parts") or []
        for part in parts:
            call = part.get("functionCall") if isinstance(part, dict) else None
            if call and call.get("name"):
                names.append(call["name"])
    return names


def seed_codes(path: Path) -> set[str]:
    return {item["codigo"] for item in json.loads(path.read_text(encoding="utf-8"))}
