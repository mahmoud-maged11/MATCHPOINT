"""MATCHPOINT dbt execution entry point.

Disable PostgreSQL JIT by default for the warehouse workload.
The setting applies only to the launched dbt process and its
database connections.

Set MATCHPOINT_DBT_JIT=on to enable JIT when benchmarking
or evaluating larger workloads.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent

JIT_ENV_VAR = "MATCHPOINT_DBT_JIT"

DEFAULT_JIT_MODE = "off"


def build_environment() -> dict[str, str]:
    """Build an isolated environment for the dbt subprocess."""

    environment = os.environ.copy()

    jit_mode = environment.get(
        JIT_ENV_VAR,
        DEFAULT_JIT_MODE,
    ).strip().lower()

    if jit_mode not in {"on", "off"}:
        raise ValueError(
            f"{JIT_ENV_VAR} must be 'on' or 'off'."
        )

    existing_options = environment.get(
        "PGOPTIONS",
        "",
    ).strip()

    jit_option = f"-c jit={jit_mode}"

    environment["PGOPTIONS"] = " ".join(
        option
        for option in (existing_options, jit_option)
        if option
    )

    return environment


def build_command(arguments: list[str]) -> list[str]:
    """Build the dbt command using the current Python environment."""

    executable_name = (
        "dbt.exe" if os.name == "nt" else "dbt"
    )

    executable = (
        Path(sys.executable).parent / executable_name
    )

    if not executable.is_file():
        raise FileNotFoundError(
            "dbt executable not found in the current Python "
            "environment. Install dbt/requirements.txt first."
        )

    return [
        str(executable),
        *arguments,
    ]


def main(arguments: list[str] | None = None) -> int:
    """Execute dbt and propagate its exit code."""

    if arguments is None:
        arguments = sys.argv[1:]

    if not arguments:
        print(
            "Usage: python dbt/run_dbt.py <dbt-command> [options]",
            file=sys.stderr,
        )
        return 2

    try:
        environment = build_environment()

        command = build_command(arguments)

        result = subprocess.run(
            command,
            cwd=PROJECT_DIR,
            env=environment,
            check=False,
        )

        return result.returncode

    except (ValueError, OSError) as exc:
        print(
            f"MATCHPOINT dbt runner error: {exc}",
            file=sys.stderr,
        )
        return 2

    except KeyboardInterrupt:
        print(
            "\nMATCHPOINT dbt execution interrupted.",
            file=sys.stderr,
        )
        return 130


if __name__ == "__main__":
    raise SystemExit(main())