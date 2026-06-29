"""
Example: build and simulate a resistor voltage divider via the Python API directly.

This shows how the qucs_mcp modules work without going through MCP.
Run with: uv run python examples/voltage_divider.py
"""

from pathlib import Path
import tempfile

from qucs_mcp.config import QucsConfig
from qucs_mcp.netlist import write_netlist
from qucs_mcp.results import parse_dat_file
from qucs_mcp.schematic import Component, Schematic, SimCommand, write_sch
from qucs_mcp.simulator import run_simulation


def main() -> None:
    config = QucsConfig()
    print(f"Using Qucs at: {config.home}")

    sch = Schematic(
        name="voltage_divider",
        components=[
            Component(
                type="Vdc",
                name="V1",
                nodes=["_net0", "gnd"],
                params={"U": "Vin", "SIL": "SIL-2"},
            ),
            Component(
                type="R",
                name="R1",
                nodes=["_net0", "_net1"],
                params={"R": "10k", "Temp": "26.85", "Tnom": "26.85", "footprint": "SMD0603"},
            ),
            Component(
                type="R",
                name="R2",
                nodes=["_net1", "gnd"],
                params={"R": "10k", "Temp": "26.85", "Tnom": "26.85", "footprint": "SMD0603"},
            ),
        ],
        sim_commands=[
            SimCommand(
                type="DC",
                name="DC1",
                params={"reltol": "0.001", "abstol": "1 nA", "temp": "26.85", "solver": "none"},
            ),
            SimCommand(
                type="SW",
                name="Sweep1",
                params={
                    "base": "DC1",
                    "var": "Vin",
                    "mode": "lin",
                    "start": "0",
                    "stop": "10V",
                    "steps": "11",
                },
            ),
        ],
    )

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        sch_path = tmp_path / "voltage_divider.sch"
        netlist_path = tmp_path / "voltage_divider.txt"
        dat_path = tmp_path / "voltage_divider.dat"

        write_sch(sch, sch_path)
        write_netlist(sch, sch_path, netlist_path)
        print(f"Wrote netlist: {netlist_path}")
        print(netlist_path.read_text())

        result = run_simulation(netlist_path, dat_path, config)
        print(f"Simulation complete. stdout: {result.stdout.strip()}")

        variables = parse_dat_file(dat_path)
        print(f"\nSimulation results ({len(variables)} variables):")
        for name, var in variables.items():
            print(f"  {name}: {var.data[:5]}{'...' if len(var.data) > 5 else ''}")


if __name__ == "__main__":
    main()
