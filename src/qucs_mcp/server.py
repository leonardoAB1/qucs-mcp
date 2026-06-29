"""
qucs-mcp MCP server entry point.

Registers all Phase 1 tools with a single FastMCP instance and runs the
stdio JSON-RPC loop. Tools are plain synchronous functions; FastMCP handles
the async wrapping and schema generation from type hints.

Logging goes to stderr only - stdout is reserved for MCP JSON-RPC messages.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from qucs_mcp.config import QucsConfig
from qucs_mcp.netlist import write_netlist
from qucs_mcp.results import parse_dat_file
from qucs_mcp.schematic import Component, Schematic, SimCommand, write_sch
from qucs_mcp.simulator import run_simulation as _run_simulation
from qucs_mcp.utils import QucsConfigError, SimulationError, SimulationTimeoutError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FastMCP server instance
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "qucs-mcp",
    instructions=(
        "MCP server for Qucs/uSimmics circuit simulation. "
        "Use create_schematic to build a circuit, run_simulation to simulate it, "
        "and read_simulation_results to retrieve the output data."
    ),
)

# Config is resolved once at import time so startup failures surface immediately.
try:
    _config = QucsConfig()
except QucsConfigError as exc:
    logger.critical("QucsConfig error: %s", exc)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Helper: project directory management
# ---------------------------------------------------------------------------

def _project_dir(project: str) -> Path:
    """Return (and create) the .qucs project directory for *project*."""
    name = project if project.endswith("_prj") else f"{project}_prj"
    path = _config.projects / name  # type: ignore[operator]
    path.mkdir(parents=True, exist_ok=True)
    return path


# ---------------------------------------------------------------------------
# Tool: create_project
# ---------------------------------------------------------------------------

@mcp.tool()
def create_project(name: str) -> dict[str, str]:
    """
    Create a new Qucs project directory under the .qucs projects folder.

    Returns the absolute path to the created project directory.
    """
    project_dir = _project_dir(name)
    return {"project_path": str(project_dir), "name": name}


# ---------------------------------------------------------------------------
# Tool: list_project_files
# ---------------------------------------------------------------------------

@mcp.tool()
def list_project_files(project: str) -> dict[str, Any]:
    """
    List all schematic, netlist, and simulation result files in a project.

    Returns file paths grouped by type: schematics (.sch), netlists (.txt/.net),
    data files (.dat), and display files (.dpl).
    """
    project_dir = _project_dir(project)
    if not project_dir.exists():
        return {"error": f"Project '{project}' not found at {project_dir}"}

    result: dict[str, list[str]] = {
        "schematics": [],
        "netlists": [],
        "data": [],
        "displays": [],
        "other": [],
    }
    for f in sorted(project_dir.iterdir()):
        if f.suffix == ".sch":
            result["schematics"].append(str(f))
        elif f.suffix in (".txt", ".net"):
            result["netlists"].append(str(f))
        elif f.suffix == ".dat":
            result["data"].append(str(f))
        elif f.suffix == ".dpl":
            result["displays"].append(str(f))
        else:
            result["other"].append(str(f))

    return {"project_path": str(project_dir), "files": result}


# ---------------------------------------------------------------------------
# Tool: list_components
# ---------------------------------------------------------------------------

@mcp.tool()
def list_components(category: str | None = None) -> dict[str, Any]:
    """
    List available Qucs component types from the installation's library files.

    Optionally filter by *category* (e.g. "Transistors", "OpAmps").
    Returns component names, descriptions, and model identifiers.
    """
    lib_dir = _config.library_dir
    if not lib_dir.exists():
        return {"error": f"Library directory not found: {lib_dir}"}

    results: dict[str, list[dict[str, str]]] = {}

    for lib_file in sorted(lib_dir.glob("*.lib")):
        text = lib_file.read_text(encoding="utf-8", errors="replace")
        current_category = lib_file.stem
        components: list[dict[str, str]] = []

        lines = iter(text.splitlines())
        for line in lines:
            if line.startswith("<Component "):
                comp_name = line.removeprefix("<Component ").removesuffix(">").strip()
                desc = ""
                model = ""
                for inner in lines:
                    inner = inner.strip()
                    if inner.startswith("<Description>"):
                        desc = inner.removeprefix("<Description>").removesuffix("</Description>").strip()
                    elif inner.startswith("<Model>"):
                        model = inner.removeprefix("<Model>").strip().split()[0]
                    elif inner == "</Component>":
                        break
                components.append({"name": comp_name, "description": desc, "model": model})

        if components:
            if category is None or category.lower() in current_category.lower():
                results[current_category] = components

    return {"categories": results, "total_components": sum(len(v) for v in results.values())}


# ---------------------------------------------------------------------------
# Tool: create_schematic
# ---------------------------------------------------------------------------

@mcp.tool()
def create_schematic(
    name: str,
    components: list[dict[str, Any]],
    simulation: dict[str, Any],
    project: str = "default",
) -> dict[str, Any]:
    """
    Generate a Qucs schematic (.sch) and netlist (.txt) ready for simulation.

    Args:
        name: Base name for the schematic file (no extension).
        components: List of component dicts, each with:
            - type (str): "R", "C", "L", "Vdc", "Idc", "_BJT", "GND", etc.
            - name (str): Instance name like "R1", "V1".
            - nodes (list[str]): Ordered net names for each pin. Use "gnd" for ground.
            - params (dict[str,str]): Parameter name -> value. Example: {"R": "1k"}.
        simulation: Dict describing the simulation, with:
            - type (str): "DC", "AC", "TR" (transient), or "SW" (sweep).
            - name (str): Instance name like "DC1".
            - params (dict[str,str]): Simulation parameters in order.
              DC example: {"reltol": "0.001", "abstol": "1 nA", "temp": "26.85", "solver": "none"}
              SW example: {"base": "DC1", "var": "Vin", "mode": "lin", "start": "0", "stop": "5V", "steps": "51"}
        project: Project name (a directory under ~/.qucs will be created).

    Returns:
        Paths to the generated .sch and netlist files, and the project directory.
    """
    project_dir = _project_dir(project)

    comps = [
        Component(
            type=c["type"],
            name=c.get("name", c["type"] + "1"),
            nodes=c.get("nodes", []),
            params=c.get("params", {}),
        )
        for c in components
    ]

    sim = SimCommand(
        type=simulation["type"],
        name=simulation.get("name", simulation["type"] + "1"),
        params=simulation.get("params", {}),
    )

    sch = Schematic(name=name, components=comps, sim_commands=[sim])

    sch_path = project_dir / f"{name}.sch"
    netlist_path = project_dir / f"{name}.txt"

    write_sch(sch, sch_path)
    write_netlist(sch, sch_path, netlist_path)

    return {
        "sch_path": str(sch_path),
        "netlist_path": str(netlist_path),
        "project_dir": str(project_dir),
    }


# ---------------------------------------------------------------------------
# Tool: run_simulation
# ---------------------------------------------------------------------------

@mcp.tool()
def run_simulation(
    netlist_path: str,
    output_path: str | None = None,
    timeout: int | None = None,
) -> dict[str, Any]:
    """
    Run the Qucs simulator on a netlist file and produce a .dat results file.

    Args:
        netlist_path: Absolute path to the .txt netlist (from create_schematic).
        output_path: Where to write the .dat file. Defaults to same directory
            as the netlist with a .dat extension.
        timeout: Override the simulation timeout in seconds (default: QUCS_SIM_TIMEOUT).

    Returns:
        dat_path (str), stdout (str), and success (bool).
    """
    nl = Path(netlist_path)
    out = Path(output_path) if output_path else nl.with_suffix(".dat")

    try:
        result = _run_simulation(nl, out, _config, timeout=timeout)
    except SimulationTimeoutError as exc:
        return {"success": False, "error": str(exc), "dat_path": None, "stdout": ""}
    except SimulationError as exc:
        return {"success": False, "error": str(exc), "dat_path": None, "stdout": ""}

    return {
        "success": True,
        "dat_path": str(result.output_path),
        "stdout": result.stdout,
    }


# ---------------------------------------------------------------------------
# Tool: read_simulation_results
# ---------------------------------------------------------------------------

@mcp.tool()
def read_simulation_results(dat_path: str) -> dict[str, Any]:
    """
    Parse a Qucs .dat simulation results file and return structured data.

    Returns a dictionary of variable names to their numeric data arrays,
    dependency information, and a flag for complex (AC) data.

    Args:
        dat_path: Absolute path to the .dat file produced by run_simulation.
    """
    path = Path(dat_path)
    if not path.exists():
        return {"error": f"File not found: {dat_path}"}

    try:
        variables = parse_dat_file(path)
    except Exception as exc:
        return {
            "error": str(exc),
            "raw_hex": path.read_bytes()[:256].hex(),
        }

    return {
        "variables": {
            name: {
                "data": var.data,
                "dependencies": var.dependencies,
                "is_complex": var.is_complex,
                "n_points": len(var.data),
            }
            for name, var in variables.items()
        },
        "n_variables": len(variables),
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
