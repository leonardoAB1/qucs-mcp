<project>
# qucs-mcp

MCP server that bridges Claude (and any MCP-compatible AI) with the Qucs/uSimmics
circuit simulator. Enables AI to generate schematics, run simulations headlessly,
and parse results - tasks that fail without programmatic access to Qucs.

- **GitHub:** https://github.com/leonardoAB1/qucs-mcp
- **Local folder:** `qucs-mcp`
- **Simulator:** uSimmics 5.9 from https://qucsstudio.de
</project>

<stack>
- **Language:** Python 3.11
- **Package manager:** uv (use `uv sync`, `uv run`, `uv add` - never pip)
- **MCP SDK:** mcp[cli] >= 1.3.0 (FastMCP high-level API)
- **Validation:** pydantic + pydantic-settings
- **Linting:** ruff
- **Type checking:** mypy
- **Testing:** pytest + pytest-asyncio
- **Build backend:** hatchling (pyproject.toml)
</stack>

<qucs>
## Critical: simulator.exe requires a netlist, not a .sch file

The Qucs GUI converts .sch -> netlist internally before calling simulator.exe.
Since this MCP is headless, it generates netlists directly. Both .sch (GUI visualization)
and .txt (netlist for simulation) are generated from the same Python Schematic model.

## Verified netlist format

```
# QucsStudio 5.9  C:/Users/ZEPHYRUS/.qucs/project_prj/schematic.sch

Vdc:V1 _net0 gnd "Vin" "SIL-2"
R:R1 _net0 _net1 "1k" "26.85" "european" "SMD0603"
R:R2 _net1 gnd "1k" "26.85" "european" "SMD0603"
.DC:DC1 "0.001" "1 nA" "26.85" "none"
.SW:Sweep1 "DC1" "Vin" "lin" "0" "10V" "11"
```

Rules:
- Ground node is always `gnd`
- Internal auto-named nets: `_net0`, `_net1`, ...
- Named nets (like `Output`, `Vin`) can be used directly
- GND components in .sch have no equivalent line in the netlist
- All parameter values in double quotes, space-separated

## Simulator CLI

```
simulator.exe -n NETLIST.txt -o OUTPUT.dat
```

Exit code 0 = success. Progress codes printed to stdout (M0 M2 M3).

## Environment variables

- `QUCS_HOME` - root of the uSimmics install (e.g. `C:\Program Files\uSimmics`)
- `QUCS_PROJECTS` - override projects dir (default: `%HOMEPATH%\.qucs`)
- `QUCS_SIM_TIMEOUT` - simulation timeout in seconds (default: 60)

## .dat file format

Binary format: 8-byte magic "QucsData" + null-separated ASCII metadata header +
packed IEEE 754 doubles (little-endian, 64-bit).
'!' prefix in metadata = real data. 'W' prefix = complex (AC) data.

## Project directories

Qucs expects projects at `%HOMEPATH%\.qucs\<name>_prj\`.
The `create_project` tool creates these directories.
</qucs>

<tools>
## Phase 1 tools (implemented)

| Tool | Description |
|------|-------------|
| `create_schematic` | Generate .sch + netlist from component + simulation dicts |
| `run_simulation` | Call simulator.exe on a netlist, return .dat path |
| `read_simulation_results` | Parse .dat binary output into structured data |
| `create_project` | Create a .qucs project directory |
| `list_project_files` | List .sch/.dat/.txt files in a project |
| `list_components` | Parse .lib files to list available component types |

## Phase 2 (planned)

- `parse_kicad_schematic` - Parse .kicad_sch S-expression format
- `kicad_to_qucs_schematic` - Convert KiCad schematic to Qucs .sch + netlist

## Phase 3 (planned)

- `extract_circuit_from_image` - Structure Claude's vision output as a Schematic object
</tools>

<architecture>
## File roles

```
src/qucs_mcp/
  server.py      - FastMCP instance, @mcp.tool() registrations, entry point
  config.py      - QucsConfig (pydantic-settings), QUCS_HOME auto-discovery
  schematic.py   - Component/SimCommand dataclasses + .sch file writer
  netlist.py     - Netlist text generator from Schematic model
  simulator.py   - subprocess wrapper for simulator.exe
  results.py     - Binary .dat file parser
  kicad.py       - .kicad_sch S-expression parser (Phase 2)
  utils.py       - Custom exceptions (QucsError, SimulationError, etc.)
```

## Data flow

1. User (or AI) calls `create_schematic` with component + simulation dicts
2. server.py builds a `Schematic` object, calls `write_sch` + `write_netlist`
3. `run_simulation` calls `simulator.exe -n netlist.txt -o output.dat`
4. `read_simulation_results` calls `parse_dat_file` and returns structured data
5. The AI can now reason about the numeric results

## Design rule: single source of truth

The `Schematic` dataclass in `schematic.py` is the authoritative model.
Never write .sch or netlist content directly in `server.py` - always go through
the model -> writer pipeline so changes propagate to both output formats.
</architecture>

<git>
Follow the Conventional Commits standard. Every commit message must:
- Be a single sentence, lowercase, no period at the end
- Use the format: `type: short description`
- Never include AI tool signatures, co-author lines, or attribution footers

**Allowed types:**
- `feat:` - new tool or capability
- `fix:` - bug fix
- `chore:` - tooling, config, dependencies
- `style:` - formatting, no logic change
- `refactor:` - restructuring without behavior change
- `docs:` - content or documentation
- `perf:` - performance improvements
- `test:` - adding or updating tests

**Examples:**
```
feat: add kicad schematic parser
fix: handle spaces in QUCS_HOME path on Windows
chore: add ruff configuration to pyproject.toml
test: add integration test for voltage divider simulation
```

**Branch naming:** `type/issueNumber-short-description`
Examples: `feat/2-kicad-import`, `fix/5-dat-parser-complex`

**PR workflow:** each PR references its issue. Squash merge into `main`.
</git>

<worktree>
Every feature, fix, or non-trivial change must be developed in a dedicated git worktree.

```
Projects\
  qucs-mcp\                      <- main repo (main branch only)
  qucs-mcp\worktrees\            <- all worktrees live here (gitignored)
    feat\
      2-kicad-import\            <- worktree for branch feat/2-kicad-import
    fix\
      5-dat-parser\              <- worktree for branch fix/5-dat-parser
```

Creating a worktree:
```powershell
git worktree add "worktrees\feat\2-kicad-import" feat/2-kicad-import
```

Removing after merge:
```powershell
git worktree remove "worktrees\feat\2-kicad-import"
git branch -d feat/2-kicad-import
```
</worktree>

<writing>
- **No em dashes.** Use a regular hyphen (-) if a separator is needed.
- This applies everywhere: commit messages, code comments, docstrings, and any generated text.
</writing>

<collaboration>
Leonardo is a robotics/mechatronics engineer who is comfortable with Python and systems
programming, but is new to Python packaging (pyproject.toml, uv, hatchling) and the MCP
protocol.

### For EVERY implementation, explain:

1. **What** you are doing and why
2. **Why** this approach is considered good practice
3. **Alternatives** that exist and their tradeoffs
4. **How** this fits into the MCP architecture
5. **Python packaging concepts** when relevant (src layout, entry points, uv vs pip)

### Key concepts to explain when they appear:

- FastMCP vs low-level JSON-RPC server (why we use FastMCP)
- Why `src/` layout instead of flat package layout
- How `pyproject.toml` entry points work
- How pydantic-settings reads environment variables
- Why `subprocess.run` with a list (not shell=True)
- How the MCP stdio transport works (stdout reserved for JSON-RPC)
- How `uv run` creates/manages virtual environments
</collaboration>
