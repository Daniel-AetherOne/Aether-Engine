from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Literal


ApprovalStatus = Literal["PENDING_APPROVAL", "APPROVED", "REJECTED"]


@dataclass
class ApprovalRecord:
    approval_id: str
    quote_id: str
    status: ApprovalStatus
    requested_by: str
    override_pct: float
    reason: str
    created_at: str
    decided_at: Optional[str] = None

    # 6.6 — token one-time use + audit
    token_used_at: Optional[str] = None
    decision_token_hash: Optional[str] = None  # optional (for audit/debug)


class ApprovalStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self) -> None:
        with self._conn() as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS approvals (
                  approval_id TEXT PRIMARY KEY,
                  quote_id TEXT NOT NULL,
                  status TEXT NOT NULL,
                  requested_by TEXT NOT NULL,
                  override_pct REAL NOT NULL,
                  reason TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  decided_at TEXT,

                  -- 6.6 additions
                  token_used_at TEXT,
                  decision_token_hash TEXT
                )
                """
            )

            # Best-effort migrate existing DBs (SQLite ignores column existence checks)
            # We try ALTER TABLE and ignore "duplicate column" errors.
            self._maybe_add_column(con, "approvals", "token_used_at", "TEXT")
            self._maybe_add_column(con, "approvals", "decision_token_hash", "TEXT")

    @staticmethod
    def _maybe_add_column(
        con: sqlite3.Connection, table: str, col: str, col_type: str
    ) -> None:
        try:
            con.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
        except sqlite3.OperationalError as e:
            # "duplicate column name" => already migrated
            if "duplicate column name" in str(e).lower():
                return
            # If table doesn't exist yet or other issue, re-raise
            raise

    def create(self, rec: ApprovalRecord) -> None:
        with self._conn() as con:
            con.execute(
                """
                INSERT INTO approvals
                  (approval_id, quote_id, status, requested_by, override_pct, reason, created_at, decided_at,
                   token_used_at, decision_token_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rec.approval_id,
                    rec.quote_id,
                    rec.status,
                    rec.requested_by,
                    rec.override_pct,
                    rec.reason,
                    rec.created_at,
                    rec.decided_at,
                    rec.token_used_at,
                    rec.decision_token_hash,
                ),
            )

    def get(self, approval_id: str) -> ApprovalRecord:
        with self._conn() as con:
            row = con.execute(
                "SELECT * FROM approvals WHERE approval_id = ?",
                (approval_id,),
            ).fetchone()
        if not row:
            raise KeyError("APPROVAL_NOT_FOUND")
        return ApprovalRecord(**dict(row))

    # 6.6 — one-time decision: approve/reject is atomic + idempotent
    def decide_once(
        self,
        approval_id: str,
        new_status: ApprovalStatus,
        *,
        decision_token_hash: Optional[str] = None,
    ) -> ApprovalRecord:
        """
        Atomically:
        - if already terminal (APPROVED/REJECTED) => return unchanged
        - if token already used => return unchanged
        - else set status + decided_at + token_used_at (+ optional token hash)

        This makes approve/reject:
        - idempotent (repeat clicks safe)
        - one-time (first token use wins)
        - immutable after terminal state
        """
        # Validate status input
        if new_status not in ("APPROVED", "REJECTED"):
            raise ValueError("new_status must be APPROVED or REJECTED")

        now = datetime.now(timezone.utc).isoformat()

        with self._conn() as con:
            # Use a single UPDATE with a WHERE guard:
            # - only if not terminal
            # - only if token_used_at is NULL
            cur = con.execute(
                """
                UPDATE approvals
                SET status = ?,
                    decided_at = COALESCE(decided_at, ?),
                    token_used_at = COALESCE(token_used_at, ?),
                    decision_token_hash = COALESCE(decision_token_hash, ?)
                WHERE approval_id = ?
                  AND status NOT IN ('APPROVED', 'REJECTED')
                  AND token_used_at IS NULL
                """,
                (new_status, now, now, decision_token_hash, approval_id),
            )

            # If nothing changed, it's either:
            # - already terminal, or
            # - token already used, or
            # - approval_id not found
            if cur.rowcount == 0:
                # ensure exists
                _ = self.get(approval_id)
                return _

        return self.get(approval_id)
