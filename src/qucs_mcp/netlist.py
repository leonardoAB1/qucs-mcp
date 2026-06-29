"""
Qucs netlist (.txt) generator.

simulator.exe requires this format, NOT the .sch file.
The GUI normally converts .sch -> netlist internally before calling the simulator.
Since this MCP is headless, we generate the netlist directly from the Schematic model.

Verified format (from C:\\Users\\ZEPHYRUS\\.qucs\\netlist.txt):

    # QucsStudio 5.9  /path/to/schematic.sch

    Vdc:Vdd _net0 gnd "5 V" "SIL-2" "SIL-2"
    R:R1 _net0 _net1 "1k" "26.85" "european" "SMD0603"
    _BJT:T1 _net2 _net3 gnd "npn" ...
    .DC:DC1 "0.001" "1 nA" "300" "none"
    .SW:Sweep1 "DC1" "Vin" "lin" "-5V" "5V" "51"

Rules:
  - Ground node is always 'gnd'
  - Auto-named internal nets: _net0, _net1, ...
  - No quotes around node names
  - All parameter values in double quotes, space-separated
  - Simulation commands prefixed with '.'
"""

from __future__ import annotations

from pathlib import Path

from qucs_mcp.schematic import Schematic

_NETLIST_VERSION = "5.9"


def _param_str(params: dict[str, str]) -> str:
    return " ".join(f'"{v}"' for v in params.values())


def write_netlist(sch: Schematic, sch_path: Path, netlist_path: Path) -> None:
    """
    Write a Qucs netlist text file to *netlist_path*.

    *sch_path* is embedded in the header comment only; it does not need to exist.
    """
    lines: list[str] = [
        f"# QucsStudio {_NETLIST_VERSION}  {sch_path.as_posix()}",
        "",
    ]

    for comp in sch.components:
        if comp.type == "GND":
            # GND components are encoded as ground connections on other components;
            # we don't emit a separate GND line in the netlist.
            continue

        nodes_str = " ".join(comp.nodes)
        params_str = _param_str(comp.params) if comp.params else ""
        line = f"{comp.type}:{comp.name} {nodes_str}"
        if params_str:
            line += f" {params_str}"
        lines.append(line)

    for cmd in sch.sim_commands:
        params_str = _param_str(cmd.params) if cmd.params else ""
        line = f".{cmd.type}:{cmd.name}"
        if params_str:
            line += f" {params_str}"
        lines.append(line)

    # The simulator requires LF-only line endings; Windows default (CRLF) breaks parsing.
    netlist_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
