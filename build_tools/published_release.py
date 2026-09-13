"""Download and exercise assets from an existing GitHub Release."""

from __future__ import annotations

import re
from pathlib import Path

from . import configuration, smoke_tests, upstream
from .ci_support import recreate, run


def verify_assets(archive: Path, checksum: Path) -> None:
    if not archive.is_file():
        raise RuntimeError(f"published release ZIP is missing: {archive}")
    if not checksum.is_file():
        raise RuntimeError(f"published release checksum is missing: {checksum}")
    lines = [line.strip() for line in checksum.read_text(encoding="ascii").splitlines() if line.strip()]
    if len(lines) != 1:
        raise RuntimeError(f"published release checksum must contain one entry: {checksum}")
    match = re.fullmatch(r"([0-9a-fA-F]{64})\s+\*?(.+)", lines[0])
    if match is None or match.group(2) != archive.name:
        raise RuntimeError(f"published release checksum does not name {archive.name}: {checksum}")
    actual = upstream.sha256(archive)
    if actual.lower() != match.group(1).lower():
        raise RuntimeError(f"published release checksum mismatch for {archive}: expected {match.group(1)}, got {actual}")


def download_verify_and_compile(
    config_path: Path,
    upstream_dir: Path,
    tag: str,
    repository: str,
    artifacts: Path,
    fixture: Path,
) -> None:
    resolved = configuration.resolve_version(tag, upstream_dir)
    config = configuration.merged_config(config_path, Path(resolved["upstreamConfig"]), resolved["toolsetVersion"])
    archive_name = f"nsis-toolset-{resolved['toolsetVersion']}.zip"
    release_dir = artifacts / "published-release"
    recreate(release_dir)
    run(
        [
            "gh",
            "release",
            "download",
            tag,
            "--repo",
            repository,
            "--dir",
            release_dir,
            "--pattern",
            archive_name,
            "--pattern",
            f"{archive_name}.sha256",
        ]
    )
    archive = release_dir / archive_name
    checksum = release_dir / f"{archive_name}.sha256"
    verify_assets(archive, checksum)
    smoke_tests.release_package_smoke(
        config,
        archive,
        artifacts / "published package",
        artifacts / "published smoke",
        fixture,
    )
