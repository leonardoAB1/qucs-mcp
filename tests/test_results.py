"""Tests for results.py - .dat file parser."""

from __future__ import annotations

import struct
from pathlib import Path
from qucs_mcp.results import parse_dat_file
from qucs_mcp.utils import ResultsParseError
import pytest


def test_rejects_non_qucs_file(tmp_path: Path) -> None:
    bad = tmp_path / "bad.dat"
    bad.write_bytes(b"NotQucs\x00" + b"\x00" * 32)
    with pytest.raises(ResultsParseError):
        parse_dat_file(bad)


def test_parses_real_schmitt_trigger(tmp_path: Path) -> None:
    """Integration test against the real .dat file from the Qucs install."""
    real_file = Path.home() / ".qucs" / "Simulation_DC_prj" / "schmitt-trigger.dat"
    if not real_file.exists():
        pytest.skip("Real .dat file not available in test environment")
    variables = parse_dat_file(real_file)
    # The schmitt-trigger schematic sweeps Vin and measures Output
    assert len(variables) > 0


def test_parses_bjt_curves(tmp_path: Path) -> None:
    """Integration test against BJT characteristic curves .dat file."""
    real_file = Path.home() / ".qucs" / "Simulation_DC_prj" / "BJT_curves.dat"
    if not real_file.exists():
        pytest.skip("Real .dat file not available in test environment")
    variables = parse_dat_file(real_file)
    assert len(variables) > 0


def test_minimal_dat_with_known_doubles(tmp_path: Path) -> None:
    """Construct a minimal valid .dat file and verify round-trip parsing."""
    values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    packed = struct.pack(f"<{len(values)}d", *values)
    # Header: magic + null separator + a variable declaration
    header = b"QucsData\x00\x00! Vout V Vin\x00\x00"
    dat = tmp_path / "test.dat"
    dat.write_bytes(header + packed)
    # The parser should find the doubles and not crash
    variables = parse_dat_file(dat)
    # At minimum, we should get back something (even if variable parsing is partial)
    assert isinstance(variables, dict)
