from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import yaml

from .rule_runner import RuleRunner, RuleSet


@dataclass(frozen=True)
class LoadedRules:
    ruleset: RuleSet
    runner: RuleRunner
    mtime_ns: int


class RuleLoader:
    """
    3.7 — Hot reload rule set from disk (thread-safe).

    - Keeps last known-good ruleset active
    - On each request: checks mtime_ns; if changed -> reload + validate
    - If reload fails: logs error and keeps old active ruleset
    """

    def __init__(self, yaml_path: str):
        self.yaml_path = yaml_path
        self._lock = threading.Lock()
        self._loaded: Optional[LoadedRules] = None

        # eager initial load (fail-fast if missing)
        self._loaded = self._load_from_disk_or_raise()

    def get(self) -> LoadedRules:
        """
        Returns the current active (last-known-good) ruleset/runner.
        Performs cheap mtime check and reloads if needed.
        """
        try:
            current_mtime = self._stat_mtime_ns()
        except FileNotFoundError:
            # keep old rules if we have them, but raise if nothing loaded yet
            if self._loaded is None:
                raise
            self._log(
                f"[RuleLoader] ruleset file missing: {self.yaml_path} (keeping previous active)"
            )
            return self._loaded

        loaded = self._loaded
        if loaded is not None and current_mtime == loaded.mtime_ns:
            return loaded

        # Changed -> reload under lock
        with self._lock:
            loaded = self._loaded
            # double-check after acquiring lock
            try:
                current_mtime = self._stat_mtime_ns()
            except FileNotFoundError:
                if loaded is None:
                    raise
                self._log(
                    f"[RuleLoader] ruleset file missing after lock: {self.yaml_path} (keeping previous active)"
                )
                return loaded

            if loaded is not None and current_mtime == loaded.mtime_ns:
                return loaded

            try:
                new_loaded = self._load_from_disk_or_raise(
                    expected_mtime_ns=current_mtime
                )
            except Exception as e:
                # Invalid YAML / validation error -> keep old active
                if loaded is None:
                    raise
                self._log(f"[RuleLoader] reload failed, keeping previous active: {e!r}")
                return loaded

            self._loaded = new_loaded
            self._log(
                f"[RuleLoader] reloaded ruleset OK (mtime_ns={new_loaded.mtime_ns})"
            )
            return new_loaded

    # -----------------
    # internals
    # -----------------

    def _stat_mtime_ns(self) -> int:
        return os.stat(self.yaml_path).st_mtime_ns

    def _load_from_disk_or_raise(
        self, expected_mtime_ns: Optional[int] = None
    ) -> LoadedRules:
        """
        Load, parse YAML, validate (RuleSet.from_dict), and build Runner.
        Raises on any error.
        """
        if expected_mtime_ns is None:
            expected_mtime_ns = self._stat_mtime_ns()

        with open(self.yaml_path, "r", encoding="utf-8") as f:
            raw: Dict[str, Any] = yaml.safe_load(f) or {}

        ruleset = RuleSet.from_dict(raw)  # cross-validates executionOrder vs rules
        runner = RuleRunner(ruleset)
        return LoadedRules(ruleset=ruleset, runner=runner, mtime_ns=expected_mtime_ns)

    @staticmethod
    def _log(msg: str) -> None:
        # MVP logging: print. Later: wire into structlog/loguru etc.
        print(msg)
