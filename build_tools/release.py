"""Assemble, package, and publish NsisToolset releases."""

from __future__ import annotations

import os
from pathlib import Path

from . import packaging, staging
from .ci_support import recreate, run


def assemble(config: dict, stage: Path, hosts: Path, artifacts: Path) -> Path:
    """Add native hosts to the Windows stage and package it reproducibly."""
    for rid in ("linux-x64", "linux-arm64", "osx-x64", "osx-arm64"):
        host_artifact = hosts / f"host-{rid}"
        staging.stage_host(config, stage, rid, host_artifact / "makensis", host_artifact / "build-metadata.json")
    packaging.validate_stage(config, stage, repair_modes=True)

    dist = artifacts / "dist"
    repeat = artifacts / "repeat"
    recreate(dist)
    recreate(repeat)
    archive = packaging.package(config, stage, dist)
    repeated_archive = packaging.package(config, stage, repeat)
    if archive.read_bytes() != repeated_archive.read_bytes():
        raise RuntimeError("repeated packaging produced different ZIP bytes")
    return archive


def publish(config: dict, dist: Path) -> None:
    """Publish exactly the versioned ZIP and checksum for the current tag."""
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
            f"NSIS {config['upstreamVersion']} toolset for Windows, Linux, and macOS.",
        ]
    )


def start_post_release_tests(tag: str) -> None:
    """Dispatch the post-release workflow after publication succeeds."""
    run(
        [
            "gh",
            "workflow",
            "run",
            "post-release-test.yml",
            "--field",
            f"release-tag={tag}",
        ]
    )
