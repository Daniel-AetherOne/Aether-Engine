# aether/engine/assets.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

from jinja2 import Environment, FileSystemLoader, select_autoescape
from aether.engine.config import EngineConfig


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def fmt_usd(value: Any) -> str:
    try:
        return f"${float(value):,.2f}"
    except Exception:
        return "—"


def fmt_qty(qty: Any, unit: Any) -> str:
    try:
        q = float(qty)
        if unit in ("sqft", "ft2"):
            return f"{q:,.0f}"
        if unit in ("m2", "sqm"):
            return f"{q:,.1f}"
        if unit in ("item", "per_item"):
            return f"{int(q)}"
        return f"{q:,.2f}"
    except Exception:
        return "—"


@dataclass
class EngineAssets:
    rules: Dict[str, Any]
    jinja_env: Environment
    template_path: str


def load_assets(
    config: EngineConfig, rules: Dict[str, Any] | None = None
) -> EngineAssets:
    root = repo_root()

    if not config.template_path:
        raise ValueError("EngineConfig.template_path is required for rendering (1.5.5)")

    env = Environment(
        loader=FileSystemLoader(str(root)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    env.globals["fmt_usd"] = fmt_usd
    env.globals["fmt_qty"] = fmt_qty

    return EngineAssets(
        rules=rules or {},
        jinja_env=env,
        template_path=config.template_path,
    )
