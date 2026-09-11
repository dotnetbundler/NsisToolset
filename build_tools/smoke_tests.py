"""Fast end-to-end checks for staged NSIS compilers."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from . import toolset_operations as toolset
from .ci_support import recreate, require_version, run


def windows_stage_and_smoke(
    config: dict,
    archive: Path,
    stage: Path,
    work: Path,
    fixture: Path,
    smoke: Path,
) -> None:
    toolset.stage_windows(config, archive, stage, work)
    environment = os.environ.copy()
    environment["NSISDIR"] = str((stage / "common").resolve())
    require_version(
        [stage / "hosts/win-x86/makensis.exe", "-VERSION"],
        config["upstreamVersion"],
        env=environment,
    )
    require_version(
        ["cmd.exe", "/d", "/c", stage / "makensis.cmd", "-VERSION"],
        config["upstreamVersion"],
        env=environment,
    )
    recreate(smoke)
    shutil.copy2(fixture, smoke / fixture.name)
    run(
        [stage.resolve() / "hosts/win-x86/makensis.exe", fixture.name],
        cwd=smoke,
        env=environment,
    )
    if not (smoke / "smoke-installer.exe").is_file():
        raise RuntimeError("Windows compiler smoke test did not produce an installer")


def native_smoke(
    config: dict,
    archive: Path,
    rid: str,
    binary: Path,
    metadata: Path,
    stage: Path,
    work: Path,
    fixture: Path,
    smoke: Path,
) -> None:
    toolset.stage_windows(config, archive, stage, work)
    toolset.stage_host(config, stage, rid, binary, metadata)
    recreate(smoke)
    shutil.copy2(fixture, smoke / fixture.name)
    environment = os.environ.copy()
    environment["NSISDIR"] = str((stage / "common").resolve())
    direct = (stage / config["hosts"][rid]["binary"]).resolve()
    run([direct, fixture.name], cwd=smoke, env=environment)
    require_version(
        [stage.resolve() / "makensis", "-VERSION"],
        config["upstreamVersion"],
        cwd=smoke,
        env=environment,
    )
    if not (smoke / "smoke-installer.exe").is_file():
        raise RuntimeError(f"{rid} smoke test did not produce an installer")


def relocated_smoke(
    config: dict,
    archive: Path,
    destination: Path,
    smoke: Path,
    fixture: Path,
) -> None:
    toolset.verify_zip(archive, destination)
    recreate(smoke)
    shutil.copy2(fixture, smoke / fixture.name)
    environment = os.environ.copy()
    environment["NSISDIR"] = str((destination / "common").resolve())
    run(
        [destination.resolve() / "hosts/linux-x64/makensis", fixture.name],
        cwd=smoke,
        env=environment,
    )
    require_version(
        [destination.resolve() / "makensis", "-VERSION"],
        config["upstreamVersion"],
        cwd=smoke,
        env=environment,
    )
    if not (smoke / "smoke-installer.exe").is_file():
        raise RuntimeError("relocated smoke test did not produce an installer")
