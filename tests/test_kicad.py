"""Tests for the KiCad .kicad_sch parser and Qucs converter."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qucs_mcp.kicad import (
    KiCadSchematic,
    _coord_key,
    _parse_sexp,
    _resolve_nets,
    _tokenize,
    kicad_schematic_to_dict,
    kicad_to_qucs,
    parse_kicad_file,
)
from qucs_mcp.utils import KiCadParseError

# ---------------------------------------------------------------------------
# Voltage-divider fixture schematic (KiCad 6+ S-expression format)
#
# Circuit:  V1(5V) -- Vin -- R1(1k) -- Vmid -- R2(1k) -- gnd
#   V1 "-" is intentionally left floating (_net0) to test auto-net assignment.
#
# Absolute pin positions (rotation=0 for all symbols):
#   V1  (0,3):  "+"  -> (0,4)   "-"  -> (0,2)
#   R1  (0,7):  "1"  -> (0,8)   "2"  -> (0,6)
#   R2  (0,11): "1"  -> (0,12)  "2"  -> (0,10)
#   GND (0,12): "1"  -> (0,12)
#
# Wire (0,4)-(0,6) + label "Vin" at (0,4) -> cluster named "Vin"
# Wire (0,8)-(0,10) + label "Vmid" at (0,8) -> cluster named "Vmid"
# power:GND at (0,12) -> coordinate (0,12) gets net "gnd"
# ---------------------------------------------------------------------------

_FIXTURE_SCH = """\
(kicad_sch (version 20231120) (generator eeschema)
  (lib_symbols
    (symbol "Device:R"
      (symbol "Device:R_0_1"
        (pin passive line (at 0 1 270) (length 0.5)
          (number "1" (effects (font (size 1 1))))
        )
      )
      (symbol "Device:R_0_2"
        (pin passive line (at 0 -1 90) (length 0.5)
          (number "2" (effects (font (size 1 1))))
        )
      )
    )
    (symbol "power:GND"
      (symbol "power:GND_0_1"
        (pin power_in line (at 0 0 90) (length 0)
          (number "1" (effects (font (size 1 1))))
        )
      )
    )
    (symbol "Device:Battery"
      (symbol "Device:Battery_0_1"
        (pin passive line (at 0 1 270) (length 0.5)
          (number "+" (effects (font (size 1 1))))
        )
      )
      (symbol "Device:Battery_0_2"
        (pin passive line (at 0 -1 90) (length 0.5)
          (number "-" (effects (font (size 1 1))))
        )
      )
    )
  )
  (wire (start 0 4) (end 0 6))
  (wire (start 0 8) (end 0 10))
  (label "Vin" (at 0 4 0))
  (label "Vmid" (at 0 8 0))
  (symbol (lib_id "Device:Battery") (at 0 3 0) (unit 1)
    (property "Reference" "V1" (at 0 0 0))
    (property "Value" "5V" (at 0 0 0))
    (pin "+" (uuid "aa-01"))
    (pin "-" (uuid "aa-02"))
  )
  (symbol (lib_id "Device:R") (at 0 7 0) (unit 1)
    (property "Reference" "R1" (at 0 0 0))
    (property "Value" "1k" (at 0 0 0))
    (pin "1" (uuid "bb-01"))
    (pin "2" (uuid "bb-02"))
  )
  (symbol (lib_id "Device:R") (at 0 11 0) (unit 1)
    (property "Reference" "R2" (at 0 0 0))
    (property "Value" "1k" (at 0 0 0))
    (pin "1" (uuid "cc-01"))
    (pin "2" (uuid "cc-02"))
  )
  (symbol (lib_id "power:GND") (at 0 12 0) (unit 1)
    (property "Reference" "#PWR01" (at 0 0 0))
    (property "Value" "GND" (at 0 0 0))
    (pin "1" (uuid "dd-01"))
  )
)
"""


@pytest.fixture()
def kicad_sch_path(tmp_path: Path) -> Path:
    p = tmp_path / "divider.kicad_sch"
    p.write_text(_FIXTURE_SCH, encoding="utf-8")
    return p


@pytest.fixture()
def ksch(kicad_sch_path: Path) -> KiCadSchematic:
    return parse_kicad_file(kicad_sch_path)


# ---------------------------------------------------------------------------
# Group 1: Tokenizer
# ---------------------------------------------------------------------------


def test_tokenize_parens() -> None:
    assert _tokenize("(foo bar)") == ["(", "foo", "bar", ")"]


def test_tokenize_quoted_string() -> None:
    tokens = _tokenize('(label "hello world")')
    assert tokens == ["(", "label", "hello world", ")"]


def test_tokenize_negative_float() -> None:
    tokens = _tokenize("(at 0 -1.016 90)")
    assert tokens == ["(", "at", "0", "-1.016", "90", ")"]


def test_tokenize_empty() -> None:
    assert _tokenize("") == []


# ---------------------------------------------------------------------------
# Group 2: S-expression parser
# ---------------------------------------------------------------------------


def test_parse_sexp_simple_list() -> None:
    result = _parse_sexp("(foo bar)")
    assert result == ["foo", "bar"]


def test_parse_sexp_nested() -> None:
    result = _parse_sexp("(at 0 1 270)")
    assert result == ["at", "0", "1", "270"]


def test_parse_sexp_deep_nest() -> None:
    result = _parse_sexp('(pin (at 0 1) (number "1"))')
    assert result == ["pin", ["at", "0", "1"], ["number", "1"]]


def test_parse_sexp_unmatched_paren_raises() -> None:
    with pytest.raises(KiCadParseError):
        _parse_sexp("(foo bar")


# ---------------------------------------------------------------------------
# Group 3: File parser
# ---------------------------------------------------------------------------


def test_parse_file_component_count(ksch: KiCadSchematic) -> None:
    # 4 instances: V1, R1, R2, and #PWR01 (power:GND)
    assert len(ksch.instances) == 4


def test_parse_file_lib_symbols(ksch: KiCadSchematic) -> None:
    assert set(ksch.lib_symbols.keys()) == {"Device:R", "power:GND", "Device:Battery"}


def test_parse_file_wire_count(ksch: KiCadSchematic) -> None:
    assert len(ksch.wires) == 2


def test_parse_file_label_count(ksch: KiCadSchematic) -> None:
    assert len(ksch.labels) == 2
    texts = {lbl.text for lbl in ksch.labels}
    assert texts == {"Vin", "Vmid"}


def test_parse_file_nonexistent_raises(tmp_path: Path) -> None:
    with pytest.raises(KiCadParseError):
        parse_kicad_file(tmp_path / "missing.kicad_sch")


def test_parse_file_wrong_root_raises(tmp_path: Path) -> None:
    bad = tmp_path / "bad.kicad_sch"
    bad.write_text("(pcb_layout (version 1))", encoding="utf-8")
    with pytest.raises(KiCadParseError, match="root tag"):
        parse_kicad_file(bad)


# ---------------------------------------------------------------------------
# Group 4: Net resolution
# ---------------------------------------------------------------------------


def test_net_resolution_vin_cluster(ksch: KiCadSchematic) -> None:
    nets = _resolve_nets(ksch)
    assert nets.get(_coord_key(0, 4)) == "Vin"
    assert nets.get(_coord_key(0, 6)) == "Vin"


def test_net_resolution_vmid_cluster(ksch: KiCadSchematic) -> None:
    nets = _resolve_nets(ksch)
    assert nets.get(_coord_key(0, 8)) == "Vmid"
    assert nets.get(_coord_key(0, 10)) == "Vmid"


def test_net_resolution_gnd_from_power_symbol(ksch: KiCadSchematic) -> None:
    nets = _resolve_nets(ksch)
    assert nets.get(_coord_key(0, 12)) == "gnd"


# ---------------------------------------------------------------------------
# Group 5: Conversion
# ---------------------------------------------------------------------------


def test_conversion_component_count(ksch: KiCadSchematic) -> None:
    sch, _ = kicad_to_qucs(ksch, "divider")
    # V1, R1, R2, and the auto-added GND marker = 4
    assert len(sch.components) == 4


def test_conversion_r1_net_names(ksch: KiCadSchematic) -> None:
    sch, _ = kicad_to_qucs(ksch, "divider")
    r1 = next(c for c in sch.components if c.name == "R1")
    # pin "1" at (0,8) -> Vmid, pin "2" at (0,6) -> Vin
    assert r1.nodes == ["Vmid", "Vin"]


def test_conversion_r2_gnd_net(ksch: KiCadSchematic) -> None:
    sch, _ = kicad_to_qucs(ksch, "divider")
    r2 = next(c for c in sch.components if c.name == "R2")
    assert "gnd" in r2.nodes


def test_conversion_v1_auto_net(ksch: KiCadSchematic) -> None:
    sch, _ = kicad_to_qucs(ksch, "divider")
    v1 = next(c for c in sch.components if c.name == "V1")
    # pin "+" -> Vin, pin "-" -> auto _net0
    assert v1.nodes[0] == "Vin"
    assert v1.nodes[1].startswith("_net")


def test_conversion_no_sim_commands(ksch: KiCadSchematic) -> None:
    sch, _ = kicad_to_qucs(ksch, "divider")
    assert sch.sim_commands == []


def test_conversion_r_params(ksch: KiCadSchematic) -> None:
    sch, _ = kicad_to_qucs(ksch, "divider")
    r1 = next(c for c in sch.components if c.name == "R1")
    assert r1.params["R"] == "1k"


def test_conversion_power_symbol_skipped(ksch: KiCadSchematic) -> None:
    sch, _ = kicad_to_qucs(ksch, "divider")
    types = {c.type for c in sch.components}
    assert "power:GND" not in types
    names = {c.name for c in sch.components}
    assert "#PWR01" not in names


def test_conversion_simulation_warning_always_present(ksch: KiCadSchematic) -> None:
    _, warnings = kicad_to_qucs(ksch, "divider")
    assert any("simulation" in w.lower() for w in warnings)


def test_conversion_unknown_component_warns(tmp_path: Path) -> None:
    sch_text = _FIXTURE_SCH.replace(
        '(symbol (lib_id "Device:R") (at 0 7 0)',
        '(symbol (lib_id "Custom:Unknown") (at 0 7 0)',
    )
    p = tmp_path / "unknown.kicad_sch"
    p.write_text(sch_text, encoding="utf-8")
    ksch_mod = parse_kicad_file(p)
    _, warnings = kicad_to_qucs(ksch_mod, "unknown")
    assert any("Custom:Unknown" in w for w in warnings)


# ---------------------------------------------------------------------------
# Group 6: Dict serializer
# ---------------------------------------------------------------------------


def test_dict_serializer_keys(ksch: KiCadSchematic) -> None:
    d = kicad_schematic_to_dict(ksch)
    assert set(d.keys()) >= {
        "lib_symbols", "components", "wires", "labels",
        "component_count", "wire_count", "label_count",
    }


def test_dict_serializer_json_serializable(ksch: KiCadSchematic) -> None:
    d = kicad_schematic_to_dict(ksch)
    json.dumps(d)  # must not raise


# ---------------------------------------------------------------------------
# Group 7: Server tool functions
# ---------------------------------------------------------------------------


def test_server_tool_missing_file() -> None:
    import qucs_mcp.server as srv
    result = srv.parse_kicad_schematic("/nonexistent/path/file.kicad_sch")
    assert "error" in result


def test_server_tool_wrong_extension(tmp_path: Path) -> None:
    import qucs_mcp.server as srv
    p = tmp_path / "schematic.sch"
    p.write_text("<QucsStudio Schematic 0.0.19>", encoding="utf-8")
    result = srv.parse_kicad_schematic(str(p))
    assert "error" in result


def test_server_tool_parse_success(kicad_sch_path: Path) -> None:
    import qucs_mcp.server as srv
    result = srv.parse_kicad_schematic(str(kicad_sch_path))
    assert "components" in result
    assert result["wire_count"] == 2


def test_server_tool_kicad_to_qucs_creates_files(
    kicad_sch_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import qucs_mcp.server as srv
    monkeypatch.setattr(srv, "_project_dir", lambda _name: tmp_path)
    result = srv.kicad_to_qucs_schematic(str(kicad_sch_path), "divider")
    assert "sch_path" in result
    assert Path(result["sch_path"]).exists()
    assert Path(result["netlist_path"]).exists()
    assert result["component_count"] == 3  # V1, R1, R2 (GND marker excluded)
