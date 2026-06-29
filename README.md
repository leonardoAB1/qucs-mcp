# qucs-mcp

MCP server for [Qucs/uSimmics](https://qucsstudio.de) circuit simulation. Enables Claude
and other MCP-compatible AI assistants to generate circuit schematics, run simulations,
and parse results programmatically.

## What it does

Without this server, asking an AI to "simulate this circuit in Qucs" fails - the AI has
no way to drive the simulator. This MCP exposes tools that let the AI:

- Build a Qucs schematic from component descriptions or KiCad files
- Run the Qucs backend simulator (`simulator.exe`) headlessly
- Parse the binary `.dat` result files into readable data
- Manage Qucs projects on disk

## Prerequisites

- [uSimmics](https://qucsstudio.de) installed (download the zip, extract anywhere)
- Python 3.11+ (managed by [uv](https://docs.astral.sh/uv/))
- uv: `winget install astral-sh.uv` or `pip install uv`

## Setup

```powershell
# Clone the repo
git clone https://github.com/leonardoAB1/qucs-mcp.git
cd qucs-mcp

# Install dependencies
uv sync

# Set the path to your uSimmics installation
$env:QUCS_HOME = "C:\Program Files\uSimmics"

# Verify the server starts
uv run qucs-mcp
```

## Claude Desktop integration

Add to `%APPDATA%\Claude\claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "qucs-mcp": {
      "command": "uv",
      "args": ["--directory", "C:\\path\\to\\qucs-mcp", "run", "qucs-mcp"],
      "env": {
        "QUCS_HOME": "C:\\Program Files\\uSimmics"
      }
    }
  }
}
```

## Claude Code (CLI) integration

Add to `.claude/settings.json` in your project:

```json
{
  "mcpServers": {
    "qucs-mcp": {
      "command": "uv",
      "args": ["--directory", "C:\\path\\to\\qucs-mcp", "run", "qucs-mcp"],
      "env": {
        "QUCS_HOME": "C:\\Program Files\\uSimmics"
      }
    }
  }
}
```

## Environment variables

| Variable | Description | Default |
|----------|-------------|---------|
| `QUCS_HOME` | Root of the uSimmics installation | Auto-discovered from common paths |
| `QUCS_PROJECTS` | Directory for Qucs projects | `%HOMEPATH%\.qucs` |
| `QUCS_SIM_TIMEOUT` | Simulation timeout in seconds | `60` |

## Available tools (Phase 1)

| Tool | Description |
|------|-------------|
| `create_schematic` | Generate a .sch file and netlist from component definitions |
| `run_simulation` | Run simulator.exe on a netlist, return the .dat results path |
| `read_simulation_results` | Parse a .dat file into structured numeric data |
| `create_project` | Create a Qucs project directory under `~/.qucs` |
| `list_project_files` | List all files in a project |
| `list_components` | Browse available component types from Qucs libraries |

## Example: voltage divider via MCP

Ask Claude (with this MCP enabled):

> Create a voltage divider with R1=10k and R2=10k, supply 5V, sweep the supply from 0 to
> 10V in 11 steps, run the DC simulation, and tell me the midpoint voltage at each step.

Claude will call `create_schematic` then `run_simulation` then `read_simulation_results`
and report the values.

## Development

```powershell
uv sync --extra dev
uv run pytest                          # unit tests
uv run pytest -k integration          # integration tests (requires QUCS_HOME)
uv run ruff check src/
uv run mypy src/
uv run mcp dev src/qucs_mcp/server.py  # open MCP Inspector in browser
```

## Roadmap

- **Phase 2:** KiCad schematic import (`parse_kicad_schematic`, `kicad_to_qucs_schematic`)
- **Phase 3:** Circuit image analysis (`extract_circuit_from_image` using Claude vision)
- **Phase 4:** AC, transient, S-parameter simulation support; result plotting

## License

MIT
