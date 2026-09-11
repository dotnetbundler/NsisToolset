"""Shared process and filesystem helpers for CI tasks."""

from __future__ import annotations

import shlex
import shutil
import subprocess
from pathlib import Path


def run(
    command: list[str | Path],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    capture: bool = False,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    normalized = [str(item) for item in command]
    print(f"+ {shlex.join(normalized)}", flush=True)
    return subprocess.run(
        normalized,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=capture,
        check=check,
    )


def recreate(directory: Path) -> None:
    if directory.exists():
        shutil.rmtree(directory)
    directory.mkdir(parents=True)


def require_version(
    command: list[str | Path],
    expected: str,
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> None:
    result = run(command, cwd=cwd, env=env, capture=True)
    actual = result.stdout.strip()
    if actual != f"v{expected}":
        raise RuntimeError(f"unexpected compiler version: {actual!r}")
