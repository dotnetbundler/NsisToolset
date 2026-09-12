"""End-to-end checks that exercise toolset root launchers."""

from __future__ import annotations

import shutil
from pathlib import Path

from . import packaging, staging
from .ci_support import recreate, require_version, run


def _compile_with_launcher(config: dict, stage: Path, fixture: Path, smoke: Path, launcher: list[str | Path]) -> None:
    recreate(smoke)
    shutil.copy2(fixture, smoke / fixture.name)
    require_version([*launcher, "-VERSION"], config["upstreamVersion"], cwd=smoke)
    run([*launcher, fixture.name], cwd=smoke)
    if not (smoke / "smoke-installer.exe").is_file():
        raise RuntimeError("root launcher smoke test did not produce an installer")


def windows_smoke(config: dict, stage: Path, fixture: Path, smoke: Path) -> None:
    launcher = ["cmd.exe", "/d", "/c", stage.resolve() / "makensis.cmd"]
    _compile_with_launcher(config, stage, fixture, smoke, launcher)


def native_smoke(config: dict, rid: str, binary: Path, metadata: Path, stage: Path, fixture: Path, smoke: Path) -> None:
    staging.stage_host(config, stage, rid, binary, metadata)
    launcher = stage.resolve() / "makensis"
    launcher.chmod(0o755)
    _compile_with_launcher(config, stage, fixture, smoke, [launcher])


def release_package_smoke(config: dict, archive: Path, destination: Path, smoke: Path, fixture: Path) -> None:
    packaging.verify_zip(config, archive, destination)
    _compile_with_launcher(config, destination, fixture, smoke, [destination.resolve() / "makensis"])
