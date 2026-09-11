"""Assemble, validate, and publish release artifacts."""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

from . import packaging, staging
from .ci_support import recreate, run


def write_provenance(metadata_root: Path, upstream_version: str, output: Path) -> dict:
    hosts = {}
    for path in sorted(metadata_root.rglob("build-metadata.json")):
        item = json.loads(path.read_text(encoding="utf-8"))
        if item["rid"] in hosts:
            raise RuntimeError(f"duplicate metadata for {item['rid']}")
        hosts[item["rid"]] = item
    record = {
        "builder": "GitHub Actions",
        "repository": os.environ.get("GITHUB_REPOSITORY"),
        "commit": os.environ.get("GITHUB_SHA"),
        "workflow": os.environ.get("GITHUB_WORKFLOW"),
        "runId": os.environ.get("GITHUB_RUN_ID"),
        "runAttempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "event": os.environ.get("GITHUB_EVENT_NAME"),
        "hostBuilds": hosts,
        "windowsHost": {
            "origin": f"Verified official nsis-{upstream_version}.zip",
            "compilerPathInUpstream": "Bin/makensis.exe",
            "runtimeDependencyPathsInUpstream": ["Bin/zlib1.dll"],
            "patches": [],
        },
        "statement": (
            "Inputs are hash-pinned upstream archives. Native compilers are built "
            "without patches using the recorded parameters and runner toolchains."
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return record


def assemble(config: dict, stage: Path, hosts: Path, artifacts: Path, source_commit: str) -> None:
    for rid in ("linux-x64", "linux-arm64", "osx-x64", "osx-arm64"):
        root = hosts / f"host-{rid}"
        staging.stage_host(config, stage, rid, root / "makensis", root / "build-metadata.json")
    provenance_path = artifacts / "build-provenance.json"
    write_provenance(hosts, config["upstreamVersion"], provenance_path)
    packaging.write_build_record(config, stage, source_commit)
    packaging.write_source_record(config, stage / "SOURCE-RECORD.md")
    packaging.generate_manifest(config, stage)
    packaging.verify_manifest(stage, repair_modes=True)

    dist = artifacts / "dist"
    repeat = artifacts / "repeat"
    recreate(dist)
    recreate(repeat)
    packaging.package(config, stage, dist)
    packaging.package(config, stage, repeat)
    name = f"nsis-toolset-{config['toolsetVersion']}.zip"
    if (dist / name).read_bytes() != (repeat / name).read_bytes():
        raise RuntimeError("repeated packaging produced different ZIP bytes")
    shutil.copy2(provenance_path, dist / "build-provenance.json")
    shutil.copy2(stage / "SOURCE-RECORD.md", dist / "source-record.md")


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
    assets = sorted(path for path in dist.iterdir() if path.is_file())
    if not assets:
        raise RuntimeError(f"no release assets found in {dist}")
    notes = (
        f"Audited cross-host NSIS {config['upstreamVersion']} toolset. "
        "See source-record.md and build-provenance.json."
    )
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
