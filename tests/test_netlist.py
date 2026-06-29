"""Tests for netlist.py - netlist file generation."""

from __future__ import annotations

from pathlib import Path
from qucs_mcp.schematic import Schematic
from qucs_mcp.netlist import write_netlist


def test_write_netlist_creates_file(tmp_path: Path, simple_divider: Schematic) -> None:
    sch_path = tmp_path / "divider.sch"
    netlist_path = tmp_path / "divider.txt"
    write_netlist(simple_divider, sch_path, netlist_path)
    assert netlist_path.exists()


def test_netlist_header(tmp_path: Path, simple_divider: Schematic) -> None:
    sch_path = tmp_path / "divider.sch"
    netlist_path = tmp_path / "divider.txt"
    write_netlist(simple_divider, sch_path, netlist_path)
    first_line = netlist_path.read_text().splitlines()[0]
    assert first_line.startswith("# QucsStudio")
    assert "divider.sch" in first_line


def test_netlist_component_format(tmp_path: Path, simple_divider: Schematic) -> None:
    sch_path = tmp_path / "divider.sch"
    netlist_path = tmp_path / "divider.txt"
    write_netlist(simple_divider, sch_path, netlist_path)
    text = netlist_path.read_text()
    # R component: R:R1 _net0 Vmid "1k" ...
    assert "R:R1 _net0 Vmid" in text
    assert "R:R2 Vmid gnd" in text
    assert "Vdc:V1 _net0 gnd" in text


def test_netlist_simulation_commands(tmp_path: Path, simple_divider: Schematic) -> None:
    sch_path = tmp_path / "divider.sch"
    netlist_path = tmp_path / "divider.txt"
    write_netlist(simple_divider, sch_path, netlist_path)
    text = netlist_path.read_text()
    assert ".DC:DC1" in text
    assert ".SW:Sweep1" in text


def test_netlist_no_gnd_component_line(tmp_path: Path, simple_divider: Schematic) -> None:
    """GND components should not emit a component line in the netlist."""
    sch_path = tmp_path / "divider.sch"
    netlist_path = tmp_path / "divider.txt"
    write_netlist(simple_divider, sch_path, netlist_path)
    text = netlist_path.read_text()
    assert "GND:GND0" not in text
