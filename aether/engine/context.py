# aether/engine/context.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
import uuid
import time


@dataclass(frozen=True)
class EngineContext:
    tenant_id: str
    vertical_id: str
    lead_id: str
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    branch_id: Optional[str] = None  # v1.5 roadmap: tenant/branch context
    created_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))


@dataclass
class StepResult:
    status: str  # "OK" | "NEEDS_REVIEW" | "FAILED"
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineState:
    """
    Mutable state bag during one run.
    Keep it JSON-serializable (store in DB per step if you want).
    """

    context: EngineContext
    data: Dict[str, Any] = field(default_factory=dict)  # evolving payload
    logs: list[dict] = field(default_factory=list)  # structured log events
    status: str = "RUNNING"  # RUNNING | SUCCEEDED | NEEDS_REVIEW | FAILED
    failure_step: Optional[str] = None
