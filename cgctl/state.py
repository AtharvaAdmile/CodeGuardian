"""
Global CLI state — shared between main callback and all command modules.
Avoids threading ctx.obj through every Typer invocation.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CliState:
    offline: bool = False
    api_url: str = "http://localhost:8742"


_state = CliState()


def get_state() -> CliState:
    return _state
