"""Tests for simulator.py - subprocess wrapper for simulator.exe."""

from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from qucs_mcp.simulator import run_simulation, SimulationResult
from qucs_mcp.utils import SimulationError, SimulationTimeoutError
import subprocess


@pytest.fixture()
def mock_config(tmp_path: Path) -> MagicMock:
    cfg = MagicMock()
    cfg.simulator_exe = tmp_path / "simulator.exe"
    cfg.sim_timeout = 30
    return cfg


def test_run_simulation_calls_correct_command(mock_config: MagicMock, tmp_path: Path) -> None:
    netlist = tmp_path / "test.txt"
    netlist.write_text("# test netlist\n")
    output = tmp_path / "test.dat"

    with patch("qucs_mcp.simulator.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="M0 M2 M3", stderr="")
        result = run_simulation(netlist, output, mock_config)

    call_args = mock_run.call_args[0][0]
    assert str(mock_config.simulator_exe) in call_args
    assert str(netlist) in call_args
    assert str(output) in call_args
    assert result.success is True


def test_run_simulation_raises_on_nonzero_exit(mock_config: MagicMock, tmp_path: Path) -> None:
    netlist = tmp_path / "test.txt"
    netlist.write_text("# bad netlist\n")
    output = tmp_path / "test.dat"

    with patch("qucs_mcp.simulator.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stdout="Error", stderr="parse error")
        with pytest.raises(SimulationError):
            run_simulation(netlist, output, mock_config)


def test_run_simulation_raises_on_timeout(mock_config: MagicMock, tmp_path: Path) -> None:
    netlist = tmp_path / "test.txt"
    netlist.write_text("# slow netlist\n")
    output = tmp_path / "test.dat"

    with patch("qucs_mcp.simulator.subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=[], timeout=30)
        with pytest.raises(SimulationTimeoutError):
            run_simulation(netlist, output, mock_config)


def test_integration_voltage_divider() -> None:
    """Full end-to-end: generate a divider netlist and simulate it."""
    import os
    qucs_home = os.environ.get("QUCS_HOME", r"C:\Program Files\uSimmics")
    simulator = Path(qucs_home) / "bin" / "simulator.exe"
    if not simulator.exists():
        pytest.skip("Qucs not installed; set QUCS_HOME to run integration tests")

    from qucs_mcp.config import QucsConfig
    from qucs_mcp.schematic import Component, Schematic, SimCommand, write_sch
    from qucs_mcp.netlist import write_netlist
    from qucs_mcp.results import parse_dat_file
    import tempfile

    cfg = QucsConfig()

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        sch = Schematic(
            name="divider",
            components=[
                Component("Vdc", "V1", ["_net0", "gnd"], {"U": "Vin", "SIL": "SIL-2", "SIL2": "SIL-2"}),
                Component("R", "R1", ["_net0", "Vmid"], {"R": "1k", "Temp": "26.85", "style": "european", "footprint": "SMD0603"}),
                Component("R", "R2", ["Vmid", "gnd"], {"R": "1k", "Temp": "26.85", "style": "european", "footprint": "SMD0603"}),
            ],
            sim_commands=[
                SimCommand("DC", "DC1", {"reltol": "0.001", "abstol": "1 nA", "temp": "26.85", "solver": "none"}),
                SimCommand("SW", "Sweep1", {"base": "DC1", "var": "Vin", "mode": "lin", "start": "0", "stop": "10V", "steps": "11"}),
            ],
        )
        sch_path = tmp_path / "divider.sch"
        netlist_path = tmp_path / "divider.txt"
        dat_path = tmp_path / "divider.dat"

        write_sch(sch, sch_path)
        write_netlist(sch, sch_path, netlist_path)
        result = run_simulation(netlist_path, dat_path, cfg)

        assert result.success
        assert dat_path.exists()

        variables = parse_dat_file(dat_path)
        assert len(variables) > 0
