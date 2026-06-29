"""Shared pytest fixtures for qucs-mcp tests."""

from __future__ import annotations

import pytest
from pathlib import Path
from qucs_mcp.schematic import Component, Schematic, SimCommand


@pytest.fixture()
def simple_divider() -> Schematic:
    """A minimal voltage divider: Vdc -> R1 -> R2 -> GND, sweep Vin 0-5V."""
    return Schematic(
        name="divider",
        components=[
            Component(type="Vdc", name="V1", nodes=["_net0", "gnd"], params={"U": "Vin", "SIL": "SIL-2", "SIL2": "SIL-2"}),
            Component(type="R", name="R1", nodes=["_net0", "Vmid"], params={"R": "1k", "Temp": "26.85", "style": "european", "footprint": "SMD0603"}),
            Component(type="R", name="R2", nodes=["Vmid", "gnd"], params={"R": "1k", "Temp": "26.85", "style": "european", "footprint": "SMD0603"}),
            Component(type="GND", name="GND0", nodes=["gnd"]),
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
                params={"base": "DC1", "var": "Vin", "mode": "lin", "start": "0", "stop": "5V", "steps": "11"},
            ),
        ],
    )
