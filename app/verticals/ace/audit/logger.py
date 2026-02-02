from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Dict, Optional

from app.verticals.ace.audit_log import AuditLog, Actor, audit_db_path


@dataclass(frozen=True)
class AuditWrite:
    action_type: str
    actor: Actor
    target_type: Optional[str] = None
    target_id: Optional[str] = None
    quote_id: Optional[str] = None
    approval_id: Optional[str] = None
    reason: Optional[str] = None
    old_value: Optional[Dict[str, Any]] = None
    new_value: Optional[Dict[str, Any]] = None
    meta: Optional[Dict[str, Any]] = None
    audit_id: Optional[str] = None  # optional idempotency key


class AuditLogger:
    """
    Central audit writer.
    - Requires actor + action_type
    - Fail closed: if logging fails, raise -> request fails
    - Generates audit_id if none is given
    """

    def __init__(self, log: AuditLog):
        self._log = log

    @classmethod
    def default(cls) -> "AuditLogger":
        return cls(AuditLog(audit_db_path()))

    @staticmethod
    def _ensure_required(w: AuditWrite) -> None:
        if not w.action_type or not str(w.action_type).strip():
            raise ValueError("action_type is required")
        if w.actor is None:
            raise ValueError("actor is required")

    def log(self, w: AuditWrite) -> str:
        self._ensure_required(w)

        audit_id = w.audit_id or f"{w.action_type.lower()}:{uuid.uuid4().hex}"

        # Fail-closed: any exception propagates
        self._log.append_action(
            audit_id=audit_id,
            action_type=w.action_type,
            actor=w.actor,
            target_type=w.target_type,
            target_id=w.target_id,
            quote_id=w.quote_id,
            approval_id=w.approval_id,
            old_value=w.old_value,
            new_value=w.new_value,
            reason=w.reason,
            meta=w.meta,
        )
        return audit_id

    def log_deduped(self, w: AuditWrite) -> str:
        self._ensure_required(w)
        audit_id = w.audit_id or f"{w.action_type.lower()}:{uuid.uuid4().hex}"

        self._log.append_action_deduped(
            audit_id=audit_id,
            action_type=w.action_type,
            actor=w.actor,
            target_type=w.target_type,
            target_id=w.target_id,
            quote_id=w.quote_id,
            approval_id=w.approval_id,
            old_value=w.old_value,
            new_value=w.new_value,
            reason=w.reason,
            meta=w.meta,
        )
        return audit_id


_audit_logger: AuditLogger | None = None


def get_audit_logger() -> AuditLogger:
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger.default()
    return _audit_logger
