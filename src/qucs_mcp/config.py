"""
QucsConfig: resolves the Qucs/uSimmics installation path from environment variables
or well-known fallback locations. Validated at server startup so tools fail fast with
a clear message rather than obscure FileNotFoundError at simulation time.
"""

from __future__ import annotations

import logging
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings

from qucs_mcp.utils import QucsConfigError

logger = logging.getLogger(__name__)

# Common install locations tried in order when QUCS_HOME is not set.
_FALLBACK_PATHS: list[Path] = [
    Path(r"C:\Program Files\uSimmics"),
    Path(r"C:\Program Files (x86)\uSimmics"),
    Path(r"C:\uSimmics"),
    Path.home() / "uSimmics",
]


class QucsConfig(BaseSettings):
    """
    Settings loaded from environment variables (prefix QUCS_).

    Variables:
        QUCS_HOME          - root of the uSimmics install (e.g. C:\\Program Files\\uSimmics)
        QUCS_PROJECTS      - override for the projects dir (default: %HOMEPATH%\\.qucs)
        QUCS_SIM_TIMEOUT   - simulation wall-clock timeout in seconds (default: 60)
    """

    model_config = {"env_prefix": "QUCS_", "case_sensitive": False}

    home: Path | None = None
    projects: Path | None = None
    sim_timeout: int = 60

    @model_validator(mode="after")
    def resolve_paths(self) -> "QucsConfig":
        if self.home is None:
            for candidate in _FALLBACK_PATHS:
                if (candidate / "bin" / "simulator.exe").exists():
                    self.home = candidate
                    logger.info("Found Qucs at %s (auto-discovered)", candidate)
                    break

        if self.home is None:
            raise QucsConfigError(
                "Qucs installation not found. "
                "Set the QUCS_HOME environment variable to the uSimmics install root "
                r"(e.g. C:\Program Files\uSimmics)."
            )

        if not (self.home / "bin" / "simulator.exe").exists():
            raise QucsConfigError(
                f"simulator.exe not found under QUCS_HOME={self.home}. "
                "Check that QUCS_HOME points to the root of the uSimmics installation."
            )

        if self.projects is None:
            self.projects = Path.home() / ".qucs"

        logger.info("QucsConfig: home=%s, projects=%s", self.home, self.projects)
        return self

    @property
    def simulator_exe(self) -> Path:
        return self.home / "bin" / "simulator.exe"  # type: ignore[operator]

    @property
    def converter_exe(self) -> Path:
        return self.home / "bin" / "converter.exe"  # type: ignore[operator]

    @property
    def library_dir(self) -> Path:
        return self.home / "library"  # type: ignore[operator]
