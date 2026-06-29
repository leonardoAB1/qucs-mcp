"""
Subprocess wrapper for simulator.exe (the Qucs backend CLI).

Usage:
    result = run_simulation(netlist_path, output_path, config)

The simulator prints progress codes to stdout (M0 M2 M3) and exits 0 on success.
On failure, the error details are in stdout/stderr.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

from qucs_mcp.config import QucsConfig
from qucs_mcp.utils import SimulationError, SimulationTimeoutError

logger = logging.getLogger(__name__)


@dataclass
class SimulationResult:
    output_path: Path
    stdout: str
    returncode: int

    @property
    def success(self) -> bool:
        return self.returncode == 0


def run_simulation(
    netlist_path: Path,
    output_path: Path,
    config: QucsConfig,
    timeout: int | None = None,
) -> SimulationResult:
    """
    Run simulator.exe on *netlist_path* and write results to *output_path*.

    Raises SimulationError on non-zero exit, SimulationTimeoutError on timeout.
    All paths are converted to str() before passing to subprocess to correctly
    handle paths with spaces (e.g. C:\\Program Files\\uSimmics).
    """
    effective_timeout = timeout if timeout is not None else config.sim_timeout

    cmd = [
        str(config.simulator_exe),
        "-n", str(netlist_path),
        "-o", str(output_path),
    ]

    logger.info("Running: %s", " ".join(cmd))

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=effective_timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise SimulationTimeoutError(
            f"Simulation exceeded {effective_timeout}s timeout. "
            "Increase QUCS_SIM_TIMEOUT for complex circuits."
        ) from exc

    logger.debug("simulator stdout: %s", proc.stdout)
    if proc.stderr:
        logger.warning("simulator stderr: %s", proc.stderr)

    if proc.returncode != 0:
        raise SimulationError(
            f"simulator.exe exited with code {proc.returncode}.\n"
            f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
        )

    return SimulationResult(
        output_path=output_path,
        stdout=proc.stdout,
        returncode=proc.returncode,
    )
