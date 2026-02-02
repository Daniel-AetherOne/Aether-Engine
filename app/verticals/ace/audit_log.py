from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Union

from app.verticals.ace.domain.auth import AdminIdentity

Actor = Union[str, AdminIdentity, None]


# -----------------------------
# Model (legacy compatible)
# -----------------------------
@dataclass(frozen=True)
class AuditEvent:
    event_id: str
    event_type: str
    created_at: str
    actor: Optional[str]
    quote_id: Optional[str]
    approval_id: Optional[str]
    meta: Dict[str, Any]


# -----------------------------
# Audit log (append-only)
# -----------------------------
class AuditLog:
    """
    Immutable append-only audit log.
    - INSERT only
    - No UPDATE / DELETE (enforced via triggers)
    - event_id is PRIMARY KEY (idempotency hook)

    7.4 adds canonical fields:
      action_type, target_type, target_id, old_json, new_json, reason
    Existing callers may keep using append()/append_deduped().
    New callers should use append_action()/append_action_deduped().
    """

    # Actions that MUST include a reason (7.4)
    REASON_REQUIRED = {
        "DATA_ROLLBACK",
        "PROFILE_UPDATE",
        "OVERRIDE_REQUESTED",
    }

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init()

    # ---- internals -------------------------------------------------

    def _conn(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        return con

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _json_dumps(obj: Dict[str, Any] | None) -> str:
        import json

        return json.dumps(obj or {}, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _actor_to_str(actor: Actor) -> Optional[str]:
        if actor is None:
            return None
        if isinstance(actor, AdminIdentity):
            return actor.username
        return str(actor)

    def _ensure_columns(self, con: sqlite3.Connection) -> None:
        # Add 7.4 columns if missing (SQLite: ALTER TABLE ADD COLUMN is safe)
        cols = {
            r["name"] for r in con.execute("PRAGMA table_info(audit_events)").fetchall()
        }

        def add(name: str, sql_type: str) -> None:
            if name not in cols:
                con.execute(f"ALTER TABLE audit_events ADD COLUMN {name} {sql_type}")

        add("action_type", "TEXT")
        add("target_type", "TEXT")
        add("target_id", "TEXT")
        add("old_json", "TEXT")
        add("new_json", "TEXT")
        add("reason", "TEXT")

        # Helpful indexes for canonical queries
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_audit_action_time ON audit_events(action_type, created_at)"
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_audit_target_time ON audit_events(target_type, target_id, created_at)"
        )

    def _enforce_append_only(self, con: sqlite3.Connection) -> None:
        """
        7.6: enforce immutable storage at DB level.
        Any UPDATE/DELETE attempt aborts.
        """
        con.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_audit_no_update
            BEFORE UPDATE ON audit_events
            BEGIN
                SELECT RAISE(ABORT, 'audit_events is append-only: UPDATE is not allowed');
            END;
            """
        )
        con.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_audit_no_delete
            BEFORE DELETE ON audit_events
            BEGIN
                SELECT RAISE(ABORT, 'audit_events is append-only: DELETE is not allowed');
            END;
            """
        )

    def _init(self) -> None:
        with self._conn() as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_events (
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    actor TEXT,
                    quote_id TEXT,
                    approval_id TEXT,
                    meta_json TEXT NOT NULL
                )
                """
            )

            # Ensure schema evolution + immutable behavior are applied to old DBs too
            self._ensure_columns(con)
            self._enforce_append_only(con)

            # Legacy indexes (keep)
            con.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_quote ON audit_events(quote_id)"
            )
            con.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_approval ON audit_events(approval_id)"
            )
            con.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_type_time ON audit_events(event_type, created_at)"
            )

    def _require_reason_if_needed(
        self, action_type: Optional[str], reason: Optional[str]
    ) -> None:
        if not action_type:
            return
        if action_type in self.REASON_REQUIRED:
            if not (reason and reason.strip()):
                raise ValueError(f"reason is required for action_type={action_type}")

    # ---- legacy API ------------------------------------------------

    def append(
        self,
        *,
        event_id: str,
        event_type: str,
        actor: Actor = None,
        quote_id: Optional[str] = None,
        approval_id: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None,
        created_at: Optional[str] = None,  # kept for backward-compat; ignored
    ) -> None:
        """
        Legacy strict append.
        Raises sqlite3.IntegrityError on duplicate event_id.

        7.6: created_at is ALWAYS server-side. Incoming created_at is ignored.
        """
        _ = created_at  # explicitly ignored
        created_at = self._utc_now_iso()

        meta_json = self._json_dumps(meta or {})
        actor_str = self._actor_to_str(actor)

        with self._conn() as con:
            # Ensure 7.4 columns + triggers exist even if DB was created long ago
            self._ensure_columns(con)
            self._enforce_append_only(con)

            con.execute(
                """
                INSERT INTO audit_events
                  (event_id, event_type, created_at, actor, quote_id, approval_id, meta_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    event_type,
                    created_at,
                    actor_str,
                    quote_id,
                    approval_id,
                    meta_json,
                ),
            )

    def append_deduped(
        self,
        *,
        event_id: str,
        event_type: str,
        actor: Actor = None,
        quote_id: Optional[str] = None,
        approval_id: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None,
        created_at: Optional[str] = None,  # ignored
    ) -> None:
        """
        Legacy idempotent append.
        If event_id already exists, it is silently ignored.
        """
        try:
            self.append(
                event_id=event_id,
                event_type=event_type,
                actor=actor,
                quote_id=quote_id,
                approval_id=approval_id,
                meta=meta,
                created_at=created_at,
            )
        except sqlite3.IntegrityError:
            return

    # ---- 7.4 canonical API ----------------------------------------

    def append_action(
        self,
        *,
        audit_id: str,
        action_type: str,
        actor: Actor = None,
        target_type: Optional[str] = None,
        target_id: Optional[str] = None,
        quote_id: Optional[str] = None,
        approval_id: Optional[str] = None,
        old_value: Optional[Dict[str, Any]] = None,
        new_value: Optional[Dict[str, Any]] = None,
        reason: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None,
        created_at: Optional[str] = None,  # kept for compat; ignored
    ) -> None:
        """
        Canonical 7.4 append.
        - action_type/target/old/new/reason are first-class columns
        - meta is still available for extras

        7.6: created_at is ALWAYS server-side. Incoming created_at is ignored.
        """
        _ = created_at  # explicitly ignored
        created_at = self._utc_now_iso()

        actor_str = self._actor_to_str(actor)
        self._require_reason_if_needed(action_type, reason)

        meta_json = self._json_dumps(meta or {})
        old_json = self._json_dumps(old_value) if old_value is not None else None
        new_json = self._json_dumps(new_value) if new_value is not None else None

        # Keep legacy field populated for compatibility
        event_type = action_type

        with self._conn() as con:
            self._ensure_columns(con)
            self._enforce_append_only(con)

            con.execute(
                """
                INSERT INTO audit_events
                  (event_id, event_type, created_at, actor, quote_id, approval_id, meta_json,
                   action_type, target_type, target_id, old_json, new_json, reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    audit_id,
                    event_type,
                    created_at,
                    actor_str,
                    quote_id,
                    approval_id,
                    meta_json,
                    action_type,
                    target_type,
                    target_id,
                    old_json,
                    new_json,
                    reason.strip() if reason else None,
                ),
            )

    def append_action_deduped(
        self,
        *,
        audit_id: str,
        action_type: str,
        actor: Actor = None,
        target_type: Optional[str] = None,
        target_id: Optional[str] = None,
        quote_id: Optional[str] = None,
        approval_id: Optional[str] = None,
        old_value: Optional[Dict[str, Any]] = None,
        new_value: Optional[Dict[str, Any]] = None,
        reason: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None,
        created_at: Optional[str] = None,  # ignored
    ) -> None:
        try:
            self.append_action(
                audit_id=audit_id,
                action_type=action_type,
                actor=actor,
                target_type=target_type,
                target_id=target_id,
                quote_id=quote_id,
                approval_id=approval_id,
                old_value=old_value,
                new_value=new_value,
                reason=reason,
                meta=meta,
                created_at=created_at,
            )
        except sqlite3.IntegrityError:
            return


# -----------------------------
# Config helper
# -----------------------------
def audit_db_path() -> str:
    return os.getenv("AUDIT_DB_PATH", "audit.db")
