from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List


def _clean_step(s: str) -> str:
    # steps zijn al newline/tab-vrij via BreakdownBuilder, maar extra safety
    s = str(s).replace("\r", "").replace("\n", " ").replace("\t", " ").strip()
    return s


def format_steps_newlines(steps: Iterable[str]) -> str:
    """
    Excel export: 1 cel met newline joins.
    Consumers: gebruiken dit letterlijk (geen eigen join logic).
    """
    items = [_clean_step(s) for s in steps if str(s).strip()]
    return "\n".join(items)


def format_steps_bullets(steps: Iterable[str], bullet: str = "•") -> List[str]:
    """
    UI: bullets onder elke line. Return List[str] zodat UI makkelijk map() kan doen.
    Mail: kan ook direct joinen met newline.
    """
    items = [_clean_step(s) for s in steps if str(s).strip()]
    return [f"{bullet} {s}" for s in items]


def format_steps_bullets_text(steps: Iterable[str], bullet: str = "•") -> str:
    """
    Mail: 1 tekstblok met bullets per regel.
    """
    return "\n".join(format_steps_bullets(steps, bullet=bullet))


@dataclass(frozen=True)
class Notice:
    code: str
    message: str


def format_notices_header(title: str, notices: list[dict], bullet: str = "•") -> str:
    """
    Voor warnings/blocks in mail of bovenaan exports.
    Houd het simpel: Title + bullet list.
    """
    if not notices:
        return ""
    lines = [title]
    for n in notices:
        msg = _clean_step(n.get("message") or "")
        code = _clean_step(n.get("code") or "")
        if code and msg:
            lines.append(f"{bullet} [{code}] {msg}")
        elif msg:
            lines.append(f"{bullet} {msg}")
        elif code:
            lines.append(f"{bullet} [{code}]")
    return "\n".join(lines)
