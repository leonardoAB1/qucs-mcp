"""
Binary .dat file parser for Qucs simulation results.

File format (reverse-engineered from real files):

  Bytes 0-7:   ASCII magic "QucsData"
  Bytes 8-9:   0x00 0x00 (padding)
  Byte  10:    format version (0x01 = v1, 0x02 = v2)
  Byte  11:    flags (0x03)
  Bytes 12-15: int32 little-endian = total descriptor block length (N)
  Bytes 16 .. 16+N-1: descriptor block (variable metadata)
  Bytes 16+N .. end:  IEEE 754 doubles, little-endian, 8 bytes each

Descriptor block layout:

  Version 1 (format byte = 0x01):
    For each variable:
      [int32 type] [int32 n_points] [name\0] [dep_name\0 if type==7]
    type 5 = independent axis, type 7 = dependent (has one dependency)

  Version 2 (format byte = 0x02):
    For each variable:
      [byte type] [byte data_type] [2 bytes misc] [int32 n_points] [name\0] [dep_name\0 if type==7]
    Same type values as v1.

Dependency names appear as duplicate null-terminated strings inside the descriptor;
they are deduplicated when building the variable list.

Data block: all variable data blocks listed sequentially in descriptor order,
each block containing n_points doubles.
"""

from __future__ import annotations

import logging
import struct
from dataclasses import dataclass, field
from pathlib import Path

from qucs_mcp.utils import ResultsParseError

logger = logging.getLogger(__name__)

_MAGIC = b"QucsData"


@dataclass
class DataVariable:
    name: str
    data: list[float] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    is_complex: bool = False


def parse_dat_file(path: Path) -> dict[str, DataVariable]:
    """
    Parse a Qucs .dat file and return a mapping of variable name -> DataVariable.

    Raises ResultsParseError if the magic header is missing.
    Returns an empty dict if no variables are found.
    """
    raw = path.read_bytes()

    if not raw.startswith(_MAGIC):
        raise ResultsParseError(
            f"{path.name} does not appear to be a Qucs .dat file "
            f"(expected magic 'QucsData', got {raw[:8]!r})"
        )

    if len(raw) < 16:
        return {}

    # Header fields
    fmt_version = raw[10]
    desc_len = struct.unpack_from("<I", raw, 12)[0]
    data_start = 16 + desc_len

    if data_start > len(raw):
        logger.warning("%s: descriptor block length %d exceeds file size", path.name, desc_len)
        return {}

    desc_block = raw[16:data_start]
    names = _extract_names(desc_block)

    if not names:
        logger.warning("%s: no variable names found in descriptor block", path.name)
        return {}

    # Read all doubles from the data region
    data_bytes = raw[data_start:]
    n_doubles = len(data_bytes) // 8
    if n_doubles == 0:
        return {name: DataVariable(name=name) for name in names}

    values = list(struct.unpack_from(f"<{n_doubles}d", data_bytes))

    # Distribute evenly (all variables in these simulations have the same n_points)
    chunk = n_doubles // len(names)
    variables: dict[str, DataVariable] = {}
    for i, name in enumerate(names):
        variables[name] = DataVariable(
            name=name,
            data=values[i * chunk : (i + 1) * chunk],
        )

    logger.info(
        "Parsed %s (fmt v%d): %d variables x %d points",
        path.name, fmt_version, len(names), chunk,
    )
    return variables


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_names(desc: bytes) -> list[str]:
    """
    Extract unique null-terminated ASCII variable names from the descriptor block.

    Names are at least 2 characters, start with a letter, and contain only
    letters, digits, '.', or '_'. Dependency names (duplicates) are dropped.
    """
    names: list[str] = []
    seen: set[str] = set()
    i = 0
    length = len(desc)

    while i < length:
        b = desc[i]
        # Look for start of a potential name: letter character
        if b in _ALPHA_BYTES:
            j = i
            while j < length and desc[j] in _NAME_BYTES:
                j += 1
            candidate_len = j - i
            if candidate_len >= 2 and (j >= length or desc[j] == 0):
                try:
                    name = desc[i:j].decode("ascii")
                    if name not in seen:
                        seen.add(name)
                        names.append(name)
                except UnicodeDecodeError:
                    pass
                i = j + 1
                continue
        i += 1

    return names


# Byte sets for name parsing (pre-computed for performance)
_ALPHA_BYTES = frozenset(
    b"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
)
_NAME_BYTES = frozenset(
    b"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._"
)
