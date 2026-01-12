from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import re
from typing import Iterator, List, Optional


# -----------------------------
# Public contract (API)
# -----------------------------


class BreakdownKind(str, Enum):
    STEP = "STEP"
    CHECK = "CHECK"
    WARNING = "WARNING"
    META = "META"


class CheckStatus(str, Enum):
    OK = "OK"
    BLOCK = "BLOCK"


_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")  # e.g. BASE, MIN_MARGIN_OK, NET_COST


def _validate_code(code: str) -> str:
    if not isinstance(code, str):
        raise TypeError("breakdown code must be str")
    code = code.strip()
    if not _CODE_RE.match(code):
        raise ValueError(
            f"invalid breakdown code '{code}'. Expected UPPER_SNAKE (3-64 chars), e.g. BASE, MIN_MARGIN_OK"
        )
    return code


def _validate_message(message: str) -> str:
    if not isinstance(message, str):
        raise TypeError("breakdown message must be str")
    msg = message.strip()
    if not msg:
        raise ValueError("breakdown message must be non-empty")
    # Keep output render-safe for UI/Excel/mail
    if "\n" in msg or "\r" in msg:
        raise ValueError("breakdown message may not contain newlines")
    if "\t" in msg:
        raise ValueError("breakdown message may not contain tabs")
    # Optional: hard cap to avoid insane payloads
    if len(msg) > 240:
        raise ValueError("breakdown message too long (max 240 chars)")
    return msg


@dataclass(frozen=True)
class BreakdownEntry:
    """
    Internal entry: includes code for tests/consistency,
    but render output is string-only.
    """

    seq: int
    kind: BreakdownKind
    code: str
    message: str
    status: Optional[CheckStatus] = None


@dataclass
class Breakdown:
    """
    Attached to LineState (or any line-like object).
    Rules write into this object.

    Backward compatibility:
    - Iterating over Breakdown yields rendered strings (like the old List[str] breakdown).
      This keeps older tests working: `any("foo" in s for s in line_state.breakdown)`.
    """

    _entries: List[BreakdownEntry] = field(default_factory=list)
    _seq: int = 0

    @property
    def entries(self) -> List[BreakdownEntry]:
        # Expose a copy to avoid accidental mutation
        return list(self._entries)

    # --- Backward compatible surface (acts like list[str] for reads) ---

    def as_strings(self) -> List[str]:
        return BreakdownBuilder().build(self)

    def __iter__(self) -> Iterator[str]:
        return iter(self.as_strings())

    def __len__(self) -> int:
        return len(self._entries)

    # --- Write API (rules call these) ---

    def add_step(
        self, code: str, message: str, kind: str | BreakdownKind = BreakdownKind.STEP
    ) -> None:
        k = BreakdownKind(kind)
        if k != BreakdownKind.STEP:
            raise ValueError("add_step only supports kind='STEP'")
        self._append(kind=k, code=code, message=message, status=None)

    def add_check(
        self, code: str, message: str, status: str | CheckStatus = CheckStatus.OK
    ) -> None:
        st = CheckStatus(status)
        self._append(kind=BreakdownKind.CHECK, code=code, message=message, status=st)

    def add_warning(self, code: str, message: str) -> None:
        self._append(
            kind=BreakdownKind.WARNING, code=code, message=message, status=None
        )

    def add_meta(self, code: str, message: str) -> None:
        self._append(kind=BreakdownKind.META, code=code, message=message, status=None)

    def _append(
        self,
        *,
        kind: BreakdownKind,
        code: str,
        message: str,
        status: Optional[CheckStatus],
    ) -> None:
        c = _validate_code(code)
        m = _validate_message(message)
        if kind == BreakdownKind.CHECK and status is None:
            raise ValueError("CHECK entry requires status")
        if kind != BreakdownKind.CHECK and status is not None:
            raise ValueError("Only CHECK entries may have status")

        self._seq += 1
        self._entries.append(
            BreakdownEntry(
                seq=self._seq,
                kind=kind,
                code=c,
                message=m,
                status=status,
            )
        )


# -----------------------------
# Render / Output builder
# -----------------------------


class BreakdownBuilder:
    """
    Converts a Breakdown to the contract output: list[str]
    while keeping internal codes for tests/consistency.
    """

    def build(self, breakdown: Breakdown) -> List[str]:
        if not isinstance(breakdown, Breakdown):
            raise TypeError("BreakdownBuilder.build expects a Breakdown instance")

        # Deterministic order = insertion order (seq)
        entries = sorted(breakdown.entries, key=lambda e: e.seq)

        out: List[str] = []
        for e in entries:
            out.append(self._render(e))
        return out

    def _render(self, e: BreakdownEntry) -> str:
        if e.kind == BreakdownKind.STEP:
            return e.message

        if e.kind == BreakdownKind.CHECK:
            assert e.status is not None
            prefix = "OK" if e.status == CheckStatus.OK else "BLOCK"
            return f"{prefix}: {e.message}"

        if e.kind == BreakdownKind.WARNING:
            return f"WARNING: {e.message}"

        if e.kind == BreakdownKind.META:
            return f"META: {e.message}"

        return e.message
