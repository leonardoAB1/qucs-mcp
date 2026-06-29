"""
Qucs schematic (.sch) data model and file writer.

The Schematic / Component / SimCommand dataclasses are the single source of truth.
Both the .sch file (human-readable, opens in uSimmics GUI) and the netlist (fed to
simulator.exe) are generated outputs from this model.

.sch file format notes:
  Header:  <QucsStudio Schematic VERSION>
  Sections: <Properties>, <Symbol>, <Components>, <Wires>, <Diagrams>, <Paintings>

  Component line:
    TYPE NAME ACTIVE X Y OFFSET_X OFFSET_Y ROTATION MIRROR "param1" show_flag ...
  Simulation command line (same section):
    .TYPE NAME ACTIVE X Y OFFSET_X OFFSET_Y ROTATION MIRROR "param1" show_flag ...
  GND line (no params):
    GND * 1 X Y 0 0 0 0
  Wire line:
    X1 Y1 X2 Y2 "" 0 0 0 ""
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

_SCH_VERSION = "5.9"

# Auto-layout: components are placed in a single column, spaced this many pixels apart.
_LAYOUT_STEP_Y = 100
_LAYOUT_START_X = 150
_LAYOUT_START_Y = 100


@dataclass
class Component:
    """A single circuit element placed on the schematic."""

    type: str
    """Qucs component type: "R", "C", "L", "Vdc", "Idc", "_BJT", "GND", etc."""

    name: str
    """Instance name: "R1", "V1", "T1", etc."""

    nodes: list[str]
    """Ordered list of net names connected to this component's pins."""

    params: dict[str, str] = field(default_factory=dict)
    """Parameter name -> value string. Order matters for netlist generation."""

    x: int = _LAYOUT_START_X
    y: int = _LAYOUT_START_Y
    rotation: int = 0
    mirror: int = 0


@dataclass
class SimCommand:
    """A SPICE-style simulation directive (.DC, .AC, .TR, .SW, .SP)."""

    type: str
    """Simulation type: "DC", "AC", "TR", "SW", "SP"."""

    name: str
    """Instance name: "DC1", "Sweep1", etc."""

    params: dict[str, str] = field(default_factory=dict)
    """Ordered parameters. Meaning depends on simulation type."""

    x: int = _LAYOUT_START_X
    y: int = 400


@dataclass
class Schematic:
    """Top-level schematic object - components + simulation commands."""

    name: str
    """Base file name (no extension)."""

    components: list[Component] = field(default_factory=list)
    sim_commands: list[SimCommand] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Auto-layout helper
# ---------------------------------------------------------------------------

def _auto_layout(sch: Schematic) -> None:
    """Assign X/Y positions to components that still sit at the default position."""
    y = _LAYOUT_START_Y
    for comp in sch.components:
        if comp.x == _LAYOUT_START_X and comp.y == _LAYOUT_START_Y:
            comp.y = y
            y += _LAYOUT_STEP_Y

    y_sim = max(y + _LAYOUT_STEP_Y, 400)
    for cmd in sch.sim_commands:
        cmd.y = y_sim
        y_sim += 80


# ---------------------------------------------------------------------------
# .sch file writer
# ---------------------------------------------------------------------------

def _param_tokens(params: dict[str, str]) -> str:
    """Render parameter dict as alternating "value" 1 tokens."""
    tokens = []
    for v in params.values():
        tokens.append(f'"{v}"')
        tokens.append("1")
    return " ".join(tokens)


def write_sch(sch: Schematic, path: Path) -> None:
    """Write a Qucs .sch file to *path* from the given Schematic model."""
    _auto_layout(sch)

    lines: list[str] = [
        f"<QucsStudio Schematic {_SCH_VERSION}>",
        "<Properties>",
        "View=0,0,800,600,1,0,0",
        "Grid=10,10,1",
        "DataSet=*.dat",
        "DataDisplay=*.dpl",
        "OpenDisplay=1",
        "showFrame=0",
        "</Properties>",
        "<Symbol>",
        "</Symbol>",
        "<Components>",
    ]

    for comp in sch.components:
        if comp.type == "GND":
            lines.append(f"GND * 1 {comp.x} {comp.y} 0 0 0 0")
        else:
            params_str = _param_tokens(comp.params) if comp.params else ""
            lines.append(
                f"{comp.type} {comp.name} 1 {comp.x} {comp.y} "
                f"-26 15 {comp.rotation} {comp.mirror} {params_str}".rstrip()
            )

    for cmd in sch.sim_commands:
        params_str = _param_tokens(cmd.params) if cmd.params else ""
        lines.append(
            f".{cmd.type} {cmd.name} 1 {cmd.x} {cmd.y} "
            f"-1 41 0 0 {params_str}".rstrip()
        )

    lines += [
        "</Components>",
        "<Wires>",
        "</Wires>",
        "<Diagrams>",
        "</Diagrams>",
        "<Paintings>",
        "</Paintings>",
    ]

    path.write_text("\n".join(lines), encoding="utf-8")
