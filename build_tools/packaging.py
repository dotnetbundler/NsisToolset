"""Validate and package the final toolset."""

from __future__ import annotations

import shutil
import time
import zipfile
from pathlib import Path

from . import staging, upstream

RELEASE_ROOTS = {"common", "hosts", "makensis", "makensis.cmd"}


def executable_paths(config: dict) -> set[str]:
    return {spec["binary"] for spec in config["hosts"].values() if spec["unixExecutable"]} | {config["launchers"]["posix"]}


def validate_stage(config: dict, stage: Path, repair_modes: bool = False) -> None:
    roots = {path.name for path in stage.iterdir()}
    if roots != RELEASE_ROOTS:
        raise RuntimeError(f"unexpected toolset roots; missing={sorted(RELEASE_ROOTS - roots)}, extra={sorted(roots - RELEASE_ROOTS)}")

    common = stage / "common"
    common_items = {path.name for path in common.iterdir()}
    expected_common = set(staging.COMMON_ITEMS)
    if common_items != expected_common:
        raise RuntimeError(f"unexpected common items; missing={sorted(expected_common - common_items)}, extra={sorted(common_items - expected_common)}")
    for required in (common / "Include", common / "Plugins", common / "Stubs"):
        if not required.is_dir() or not any(required.rglob("*")):
            raise RuntimeError(f"missing or empty required common directory: {required}")

    expected_hosts = {spec["directory"] for spec in config["hosts"].values()}
    actual_hosts = {path.name for path in (stage / "hosts").iterdir()}
    if actual_hosts != expected_hosts:
        raise RuntimeError(f"unexpected host directories; missing={sorted(expected_hosts - actual_hosts)}, extra={sorted(actual_hosts - expected_hosts)}")

    for rid, spec in config["hosts"].items():
        binary = stage / spec["binary"]
        if not binary.is_file():
            raise RuntimeError(f"missing {rid} binary: {spec['binary']}")
        expected_files = set(staging.WINDOWS_RUNTIME_ITEMS) if rid == "win-x86" else {binary.name}
        host = stage / "hosts" / spec["directory"]
        actual_files = {path.name for path in host.iterdir()}
        if actual_files != expected_files or not all(path.is_file() for path in host.iterdir()):
            raise RuntimeError(f"unexpected {rid} runtime files; expected={sorted(expected_files)}, actual={sorted(actual_files)}")
        nsisdir = spec.get("requiredEnvironment", {}).get("NSISDIR", {}).get("toolsetRelativePath")
        if nsisdir != "common":
            raise RuntimeError(f"{rid} must declare NSISDIR as toolset-relative common")

    for launcher in config["launchers"].values():
        if not (stage / launcher).is_file():
            raise RuntimeError(f"missing root launcher: {launcher}")

    executables = executable_paths(config)
    for path in (item for item in stage.rglob("*") if item.is_file()):
        relative = path.relative_to(stage).as_posix()
        if relative.endswith((".py", ".bin")):
            raise RuntimeError(f"build/test file leaked into toolset: {relative}")
        if repair_modes:
            path.chmod(0o755 if relative in executables else 0o644)


def deterministic_zip(config: dict, stage: Path, destination: Path, epoch: int) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    timestamp = time.gmtime(max(epoch, 315532800))[:6]
    executables = executable_paths(config)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for path in sorted(item for item in stage.rglob("*") if item.is_file()):
            relative = path.relative_to(stage).as_posix()
            info = zipfile.ZipInfo(relative, timestamp)
            info.create_system = 3
            info.external_attr = (0o755 if relative in executables else 0o644) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            with path.open("rb") as source:
                bundle.writestr(info, source.read(), compresslevel=9)


def package(config: dict, stage: Path, dist: Path) -> Path:
    validate_stage(config, stage)
    name = f"nsis-toolset-{config['toolsetVersion']}.zip"
    archive = dist / name
    deterministic_zip(config, stage, archive, config["sourceDateEpoch"])
    checksum = upstream.sha256(archive)
    (dist / f"{name}.sha256").write_text(f"{checksum}  {name}\n", encoding="ascii", newline="\n")
    print(f"created {archive} ({checksum})")
    return archive


def verify_zip(config: dict, archive: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    upstream.safe_extract_zip_flat(archive, destination)
    validate_stage(config, destination, repair_modes=True)
