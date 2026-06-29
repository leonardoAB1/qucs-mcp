"""Tests for schematic.py - .sch file generation."""

from __future__ import annotations

from pathlib import Path
from qucs_mcp.schematic import Schematic, Component, SimCommand, write_sch


def test_write_sch_creates_file(tmp_path: Path, simple_divider: Schematic) -> None:
    out = tmp_path / "divider.sch"
    write_sch(simple_divider, out)
    assert out.exists()


def test_sch_has_required_sections(tmp_path: Path, simple_divider: Schematic) -> None:
    out = tmp_path / "test.sch"
    write_sch(simple_divider, out)
    text = out.read_text()
    for section in ("<Properties>", "<Components>", "<Wires>", "<Diagrams>", "<Paintings>"):
        assert section in text, f"Missing section: {section}"


def test_sch_contains_components(tmp_path: Path, simple_divider: Schematic) -> None:
    out = tmp_path / "test.sch"
    write_sch(simple_divider, out)
    text = out.read_text()
    assert "Vdc V1" in text
    assert "R R1" in text
    assert "R R2" in text
    assert "GND" in text


def test_sch_contains_simulation_commands(tmp_path: Path, simple_divider: Schematic) -> None:
    out = tmp_path / "test.sch"
    write_sch(simple_divider, out)
    text = out.read_text()
    assert ".DC DC1" in text
    assert ".SW Sweep1" in text


def test_sch_version_header(tmp_path: Path) -> None:
    sch = Schematic(name="empty", components=[], sim_commands=[])
    out = tmp_path / "empty.sch"
    write_sch(sch, out)
    first_line = out.read_text().splitlines()[0]
    assert first_line.startswith("<QucsStudio Schematic")
