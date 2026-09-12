"""Assemble, validate, and publish release artifacts."""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

from . import packaging, staging
from .ci_support import recreate, run


def assemble(config: dict, stage: Path, hosts: Path, artifacts: Path) -> None:
    for rid in ("linux-x64", "linux-arm64", "osx-x64", "osx-arm64"):
        root = hosts / f"host-{rid}"
        staging.stage_host(config, stage, rid, root / "makensis", root / "build-metadata.json")
    packaging.validate_stage(config, stage, repair_modes=True)

    dist = artifacts / "dist"
    repeat = artifacts / "repeat"
    recreate(dist)
    recreate(repeat)
    packaging.package(config, stage, dist)
    packaging.package(config, stage, repeat)
    name = f"nsis-toolset-{config['toolsetVersion']}.zip"
    if (dist / name).read_bytes() != (repeat / name).read_bytes():
        raise RuntimeError("repeated packaging produced different ZIP bytes")


def test_installer(installer: Path, install_root: Path) -> None:
    if not installer.is_file():
        raise RuntimeError(f"missing smoke installer: {installer}")
    if install_root.exists():
        shutil.rmtree(install_root)
    install_root.parent.mkdir(parents=True, exist_ok=True)
    run([installer.resolve(), "/S", f"/D={install_root.resolve()}"])
    marker = install_root / "installed.txt"
    if not marker.is_file():
        raise RuntimeError(f"install failed: {installer}")
    uninstaller = install_root / "uninstall.exe"
    run([uninstaller, "/S"])
    deadline = time.monotonic() + 10
    while install_root.exists() and time.monotonic() < deadline:
        time.sleep(0.25)
    if install_root.exists():
        raise RuntimeError(f"uninstall left files: {installer}")


def publish(config: dict, dist: Path) -> None:
    expected_tag = f"v{config['toolsetVersion']}"
    actual_tag = os.environ.get("GITHUB_REF_NAME")
    if actual_tag != expected_tag:
        raise RuntimeError(f"tag mismatch: expected {expected_tag}, got {actual_tag!r}")
    archive_name = f"nsis-toolset-{config['toolsetVersion']}.zip"
    expected_names = {archive_name, f"{archive_name}.sha256"}
    assets = sorted(path for path in dist.iterdir() if path.is_file())
    actual_names = {path.name for path in assets}
    if actual_names != expected_names:
        raise RuntimeError(f"unexpected release assets; missing={sorted(expected_names - actual_names)}, extra={sorted(actual_names - expected_names)}")
    notes = f"NSIS {config['upstreamVersion']} toolset for Windows, Linux, and macOS."
    run(
        [
            "gh",
            "release",
            "create",
            actual_tag,
            *assets,
            "--verify-tag",
            "--title",
            f"NSIS Toolset {config['toolsetVersion']}",
            "--notes",
            notes,
        ]
    )
