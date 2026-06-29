"""KiCad .kicad_sch S-expression parser and Qucs schematic converter."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from qucs_mcp.schematic import Component, Schematic
from qucs_mcp.utils import KiCadParseError

# ---------------------------------------------------------------------------
# S-expression tokenizer and parser
# ---------------------------------------------------------------------------


def _tokenize(text: str) -> list[str]:
    """Tokenize a KiCad S-expression string into a flat list of atoms and parens."""
    tokens: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c in " \t\r\n":
            i += 1
        elif c == "(":
            tokens.append("(")
            i += 1
        elif c == ")":
            tokens.append(")")
            i += 1
        elif c == '"':
            i += 1
            buf: list[str] = []
            while i < n and text[i] != '"':
                if text[i] == "\\" and i + 1 < n:
                    i += 1
                    buf.append(text[i])
                else:
                    buf.append(text[i])
                i += 1
            tokens.append("".join(buf))
            i += 1
        else:
            j = i
            while j < n and text[j] not in ' \t\r\n()"':
                j += 1
            tokens.append(text[i:j])
            i = j
    return tokens


def _parse_node(tokens: list[str], pos: int) -> tuple[Any, int]:
    """Recursively parse one node (atom or list) from tokens starting at pos."""
    if pos >= len(tokens):
        raise KiCadParseError("unexpected end of input")
    tok = tokens[pos]
    if tok == "(":
        pos += 1
        children: list[Any] = []
        while pos < len(tokens) and tokens[pos] != ")":
            child, pos = _parse_node(tokens, pos)
            children.append(child)
        if pos >= len(tokens):
            raise KiCadParseError("unmatched '(' - missing closing ')'")
        return children, pos + 1
    if tok == ")":
        raise KiCadParseError("unexpected ')'")
    return tok, pos + 1


def _parse_sexp(text: str) -> list[Any]:
    """Parse a KiCad S-expression string and return the top-level list."""
    tokens = _tokenize(text)
    if not tokens:
        raise KiCadParseError("empty input - file must start with '('")
    result, _ = _parse_node(tokens, 0)
    if not isinstance(result, list):
        raise KiCadParseError("top-level expression must be a list, got a bare atom")
    return result


def _find_children(node: list[Any], key: str) -> list[list[Any]]:
    """Return all direct child lists of node whose first element equals key."""
    return [c for c in node[1:] if isinstance(c, list) and c and c[0] == key]


def _find_child(node: list[Any], key: str) -> list[Any] | None:
    """Return the first direct child list of node whose first element equals key."""
    for c in node[1:]:
        if isinstance(c, list) and c and c[0] == key:
            return c
    return None


# ---------------------------------------------------------------------------
# KiCad intermediate data model
# ---------------------------------------------------------------------------


@dataclass
class KiCadPin:
    number: str
    rel_x: float
    rel_y: float


@dataclass
class KiCadLibSymbol:
    lib_id: str
    pins: list[KiCadPin]


@dataclass
class KiCadSymbolInstance:
    lib_id: str
    reference: str
    value: str
    cx: float
    cy: float
    rotation: float


@dataclass
class KiCadWire:
    x1: float
    y1: float
    x2: float
    y2: float


@dataclass
class KiCadLabel:
    text: str
    x: float
    y: float


@dataclass
class KiCadSchematic:
    lib_symbols: dict[str, KiCadLibSymbol] = field(default_factory=dict)
    instances: list[KiCadSymbolInstance] = field(default_factory=list)
    wires: list[KiCadWire] = field(default_factory=list)
    labels: list[KiCadLabel] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Section parsers
# ---------------------------------------------------------------------------


def _collect_pins(node: list[Any]) -> list[KiCadPin]:
    """Recursively collect all pin definitions from a lib symbol node."""
    pins: list[KiCadPin] = []
    for child in node[1:]:
        if not isinstance(child, list) or not child:
            continue
        if child[0] == "pin":
            at_node = _find_child(child, "at")
            number_node = _find_child(child, "number")
            if at_node is None or number_node is None:
                continue
            try:
                rel_x = float(at_node[1])
                rel_y = float(at_node[2])
                num = str(number_node[1])
            except (IndexError, ValueError):
                continue
            pins.append(KiCadPin(number=num, rel_x=rel_x, rel_y=rel_y))
        elif child[0] == "symbol":
            pins.extend(_collect_pins(child))
    return pins


def _parse_lib_symbols(node: list[Any]) -> dict[str, KiCadLibSymbol]:
    """Parse the (lib_symbols ...) section into a lib_id -> KiCadLibSymbol map."""
    result: dict[str, KiCadLibSymbol] = {}
    for sym in _find_children(node, "symbol"):
        if len(sym) < 2 or not isinstance(sym[1], str):
            continue
        lib_id = sym[1]
        result[lib_id] = KiCadLibSymbol(lib_id=lib_id, pins=_collect_pins(sym))
    return result


def _parse_instances(sym_nodes: list[list[Any]]) -> list[KiCadSymbolInstance]:
    """Parse top-level (symbol ...) instance nodes into KiCadSymbolInstance objects."""
    result: list[KiCadSymbolInstance] = []
    for node in sym_nodes:
        lib_id_node = _find_child(node, "lib_id")
        at_node = _find_child(node, "at")
        if lib_id_node is None or at_node is None:
            continue
        if len(lib_id_node) < 2 or len(at_node) < 3:
            continue
        lib_id = str(lib_id_node[1])
        try:
            cx = float(at_node[1])
            cy = float(at_node[2])
            rotation = float(at_node[3]) if len(at_node) > 3 else 0.0
        except (ValueError, IndexError):
            continue
        reference = ""
        value = ""
        for child in node[1:]:
            if not isinstance(child, list) or not child or child[0] != "property":
                continue
            if len(child) < 3:
                continue
            prop_name = str(child[1])
            prop_val = str(child[2])
            if prop_name == "Reference":
                reference = prop_val
            elif prop_name == "Value":
                value = prop_val
        if not reference:
            continue
        result.append(KiCadSymbolInstance(
            lib_id=lib_id,
            reference=reference,
            value=value,
            cx=cx,
            cy=cy,
            rotation=rotation,
        ))
    return result


def _parse_wires(wire_nodes: list[list[Any]]) -> list[KiCadWire]:
    """Parse (wire ...) nodes into KiCadWire objects."""
    result: list[KiCadWire] = []
    for node in wire_nodes:
        start = _find_child(node, "start")
        end = _find_child(node, "end")
        if start is None or end is None:
            continue
        try:
            result.append(KiCadWire(
                x1=float(start[1]),
                y1=float(start[2]),
                x2=float(end[1]),
                y2=float(end[2]),
            ))
        except (IndexError, ValueError):
            continue
    return result


def _parse_labels(label_nodes: list[list[Any]]) -> list[KiCadLabel]:
    """Parse (label ...) and (global_label ...) nodes into KiCadLabel objects.

    Handles both KiCad 6+ format (label "text" (at x y r)) and
    legacy format (label (at x y r) (text "name")).
    """
    result: list[KiCadLabel] = []
    for node in label_nodes:
        at_node = _find_child(node, "at")
        if at_node is None or len(at_node) < 3:
            continue
        if len(node) > 1 and isinstance(node[1], str):
            text: str = node[1]
        else:
            text_node = _find_child(node, "text")
            if text_node is None or len(text_node) < 2:
                continue
            text = str(text_node[1])
        try:
            x = float(at_node[1])
            y = float(at_node[2])
        except (IndexError, ValueError):
            continue
        result.append(KiCadLabel(text=text, x=x, y=y))
    return result


def parse_kicad_file(path: Path) -> KiCadSchematic:
    """Read and parse a .kicad_sch file into a KiCadSchematic."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise KiCadParseError(f"cannot read {path}: {exc}") from exc

    tree = _parse_sexp(text)

    if not tree or tree[0] != "kicad_sch":
        root_tag = tree[0] if tree else "(empty)"
        raise KiCadParseError(f"not a KiCad schematic file (root tag: {root_tag!r})")

    lib_sym_node = _find_child(tree, "lib_symbols")
    lib_symbols = _parse_lib_symbols(lib_sym_node) if lib_sym_node else {}

    wires = _parse_wires(_find_children(tree, "wire"))
    labels = _parse_labels(
        _find_children(tree, "label") + _find_children(tree, "global_label")
    )
    instances = _parse_instances(_find_children(tree, "symbol"))

    return KiCadSchematic(
        lib_symbols=lib_symbols,
        instances=instances,
        wires=wires,
        labels=labels,
    )


# ---------------------------------------------------------------------------
# Net resolution via union-find
# ---------------------------------------------------------------------------


class _UnionFind:
    def __init__(self) -> None:
        self._parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        if x not in self._parent:
            self._parent[x] = x
            return x
        root = x
        while self._parent[root] != root:
            root = self._parent[root]
        # Path compression
        node = x
        while self._parent[node] != root:
            nxt = self._parent[node]
            self._parent[node] = root
            node = nxt
        return root

    def union(self, x: str, y: str) -> None:
        rx, ry = self.find(x), self.find(y)
        if rx != ry:
            self._parent[rx] = ry

    def all_keys(self) -> set[str]:
        return set(self._parent.keys())


def _coord_key(x: float, y: float) -> str:
    """Encode a coordinate as a string key at 0.001 mm precision."""
    return f"{x:.3f},{y:.3f}"


def _rotate_pin(
    cx: float, cy: float, px: float, py: float, rot_deg: float
) -> tuple[float, float]:
    """Transform a pin's symbol-relative position to absolute schematic coordinates.

    KiCad uses Y-down screen coordinates with CCW rotation convention.
    """
    theta = math.radians(rot_deg)
    x_abs = cx + px * math.cos(theta) + py * math.sin(theta)
    y_abs = cy - px * math.sin(theta) + py * math.cos(theta)
    return x_abs, y_abs


_POWER_GROUNDS: frozenset[str] = frozenset({
    "power:GND",
    "power:GNDD",
    "power:Earth",
    "power:PWRFLAG",
})


def _resolve_nets(ksch: KiCadSchematic) -> dict[str, str]:
    """Return a mapping of coordinate keys to net names for all named wire clusters."""
    uf = _UnionFind()

    for wire in ksch.wires:
        uf.union(_coord_key(wire.x1, wire.y1), _coord_key(wire.x2, wire.y2))

    root_to_net: dict[str, str] = {}
    for label in ksch.labels:
        k = _coord_key(label.x, label.y)
        root_to_net[uf.find(k)] = label.text

    for inst in ksch.instances:
        if not inst.lib_id.startswith("power:"):
            continue
        lib_sym = ksch.lib_symbols.get(inst.lib_id)
        if lib_sym is None:
            continue
        for pin in lib_sym.pins:
            ax, ay = _rotate_pin(inst.cx, inst.cy, pin.rel_x, pin.rel_y, inst.rotation)
            k = _coord_key(ax, ay)
            root = uf.find(k)
            if inst.lib_id in _POWER_GROUNDS:
                root_to_net[root] = "gnd"
            else:
                net = inst.value.lstrip("+").replace(".", "_").replace("-", "n")
                if net:
                    root_to_net[root] = net

    return {
        k: root_to_net[uf.find(k)]
        for k in uf.all_keys()
        if uf.find(k) in root_to_net
    }


# ---------------------------------------------------------------------------
# Component type mapping and parameter builder
# ---------------------------------------------------------------------------

_COMPONENT_MAP: dict[str, str] = {
    "Device:R": "R",
    "Device:C": "C",
    "Device:C_Polarized": "C",
    "Device:L": "L",
    "Device:D": "D",
    "Device:LED": "D",
    "Device:Q_NPN_BCE": "_BJT",
    "Device:Q_PNP_BCE": "_BJT",
    "Device:Battery": "Vdc",
}


def _build_params(qucs_type: str, value: str) -> dict[str, str]:
    """Return the Qucs parameter dict for a given component type and KiCad value."""
    if qucs_type == "R":
        return {"R": value, "Temp": "26.85", "style": "european", "footprint": "SMD0603"}
    if qucs_type == "C":
        return {"C": value, "Temp": "26.85"}
    if qucs_type == "L":
        return {"L": value}
    if qucs_type == "Vdc":
        return {"U": value, "SIL": "SIL-2"}
    if qucs_type == "D":
        return {"model": value}
    if qucs_type == "_BJT":
        return {"model": value, "type": "npn"}
    return {"value": value}


def _pin_sort_key(pin: KiCadPin) -> tuple[int, str]:
    """Sort numeric pins by integer value; named pins ('+', '-') sort after."""
    try:
        return (int(pin.number), "")
    except ValueError:
        return (999, pin.number)


# ---------------------------------------------------------------------------
# Conversion: KiCadSchematic -> Schematic
# ---------------------------------------------------------------------------


def kicad_to_qucs(ksch: KiCadSchematic, name: str) -> tuple[Schematic, list[str]]:
    """Convert a KiCadSchematic to a Qucs Schematic.

    Returns (schematic, warnings). The schematic has no sim_commands because
    KiCad schematics do not contain simulation instructions.
    """
    coord_to_net = _resolve_nets(ksch)
    warnings: list[str] = []
    components: list[Component] = []
    auto_net_counter = 0
    coord_to_auto: dict[str, str] = {}
    has_gnd = False

    for inst in ksch.instances:
        if inst.lib_id.startswith("power:") or inst.reference.startswith("#"):
            continue
        qucs_type = _COMPONENT_MAP.get(inst.lib_id)
        if qucs_type is None:
            warnings.append(
                f"skipped {inst.reference} ({inst.lib_id}): unsupported component type"
            )
            continue
        lib_sym = ksch.lib_symbols.get(inst.lib_id)
        if lib_sym is None:
            warnings.append(
                f"skipped {inst.reference} ({inst.lib_id}): no pin definitions found"
            )
            continue

        nodes: list[str] = []
        for pin in sorted(lib_sym.pins, key=_pin_sort_key):
            ax, ay = _rotate_pin(inst.cx, inst.cy, pin.rel_x, pin.rel_y, inst.rotation)
            k = _coord_key(ax, ay)
            net = coord_to_net.get(k)
            if net is None:
                net = coord_to_auto.get(k)
                if net is None:
                    net = f"_net{auto_net_counter}"
                    auto_net_counter += 1
                    coord_to_auto[k] = net
            nodes.append(net)
            if net == "gnd":
                has_gnd = True

        components.append(Component(
            type=qucs_type,
            name=inst.reference,
            nodes=nodes,
            params=_build_params(qucs_type, inst.value),
        ))

    if has_gnd:
        components.append(Component(type="GND", name="GND0", nodes=["gnd"]))

    warnings.append(
        "KiCad schematics contain no simulation commands - "
        "add a simulation with create_schematic before calling run_simulation"
    )

    return Schematic(name=name, components=components, sim_commands=[]), warnings


# ---------------------------------------------------------------------------
# JSON serializer for the parse_kicad_schematic MCP tool
# ---------------------------------------------------------------------------


def kicad_schematic_to_dict(ksch: KiCadSchematic) -> dict[str, Any]:
    """Serialize a KiCadSchematic to a JSON-serializable dict (raw view, no conversion)."""
    return {
        "lib_symbols": list(ksch.lib_symbols.keys()),
        "components": [
            {
                "lib_id": inst.lib_id,
                "reference": inst.reference,
                "value": inst.value,
                "x": inst.cx,
                "y": inst.cy,
                "rotation": inst.rotation,
            }
            for inst in ksch.instances
        ],
        "wires": [
            {"x1": w.x1, "y1": w.y1, "x2": w.x2, "y2": w.y2}
            for w in ksch.wires
        ],
        "labels": [
            {"text": lbl.text, "x": lbl.x, "y": lbl.y}
            for lbl in ksch.labels
        ],
        "component_count": len(ksch.instances),
        "wire_count": len(ksch.wires),
        "label_count": len(ksch.labels),
    }
