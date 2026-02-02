# aether/engine/config.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class StepConfig:
    id: str
    use: str
    with_: Dict[str, Any]
    on_fail: str = "STOP"           # STOP | CONTINUE (meestal STOP)
    on_needs_review: str = "STOP"   # STOP | CONTINUE


@dataclass
class EngineConfig:
    vertical_id: str
    rules_path: str
    template_path: str
    steps: List[StepConfig]
    version: str = "1.0"
    defaults: Optional[Dict[str, Any]] = None


def load_engine_config(raw: Dict[str, Any]) -> EngineConfig:
    steps = []
    for s in raw["pipeline"]["steps"]:
        steps.append(
            StepConfig(
                id=s["id"],
                use=s["use"],
                with_=s.get("with", {}),
                on_fail=s.get("on_fail", "STOP"),
                on_needs_review=s.get("on_needs_review", "STOP"),
            )
        )

    return EngineConfig(
        vertical_id=raw["vertical_id"],
        rules_path=raw["assets"]["rules"],
        template_path=raw["assets"]["template"],
        steps=steps,
        version=raw.get("version", "1.0"),
        defaults=raw.get("defaults"),
    )
