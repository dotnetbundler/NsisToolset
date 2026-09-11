#!/usr/bin/env python3
"""Auditable assembly and verification for the NSIS cross-host toolset."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "toolset.json"
COMMON_ITEMS = ("Include", "Plugins", "Stubs", "Contrib", "nsisconf.nsh", "COPYING")


def load_config(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path: Path, algorithm: str) -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256(path: Path) -> str:
    return digest(path, "sha256")


def checked_file(path: Path, spec: dict) -> None:
    if not path.is_file():
        raise RuntimeError(f"missing input: {path}")
    actual_size = path.stat().st_size
    actual_sha1 = digest(path, "sha1")
    actual_sha256 = sha256(path)
    expected_sha1 = spec["digests"]["upstreamPublished"]["sha1"]
    expected_sha256 = spec["digests"]["locallyDerived"]["sha256"]
    if actual_size != spec["size"] or actual_sha1 != expected_sha1 or actual_sha256 != expected_sha256:
        raise RuntimeError(
            f"upstream verification failed for {path.name}: "
            f"size={actual_size}, sha1={actual_sha1}, sha256={actual_sha256}"
        )


def download(config: dict, cache: Path) -> None:
    cache.mkdir(parents=True, exist_ok=True)
    for name, spec in config["upstream"].items():
        destination = cache / spec["fileName"]
        if destination.exists():
            try:
                checked_file(destination, spec)
                print(f"verified cached {destination.name}")
                continue
            except RuntimeError:
                destination.unlink()
        temporary = destination.with_suffix(destination.suffix + ".partial")
        request = urllib.request.Request(spec["url"], headers={"User-Agent": "NsisToolset reproducible builder"})
        last_error: Exception | None = None
        for attempt in range(1, 4):
            try:
                with urllib.request.urlopen(request, timeout=90) as response, temporary.open("wb") as output:
                    shutil.copyfileobj(response, output)
                checked_file(temporary, spec)
                temporary.replace(destination)
                print(f"downloaded and verified {name}: {destination.name}")
                last_error = None
                break
            except Exception as error:  # network errors are reported after bounded retries
                last_error = error
                temporary.unlink(missing_ok=True)
                if attempt < 3:
                    time.sleep(attempt * 2)
        if last_error:
            raise RuntimeError(f"failed to download {spec['url']}: {last_error}")


def safe_extract_zip(archive: Path, destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        for item in bundle.infolist():
            relative = PurePosixPath(item.filename)
            if relative.is_absolute() or ".." in relative.parts:
                raise RuntimeError(f"unsafe ZIP member: {item.filename}")
        bundle.extractall(destination)
    roots = [p for p in destination.iterdir() if p.is_dir()]
    if len(roots) != 1:
        raise RuntimeError(f"expected one archive root, found {len(roots)}")
    return roots[0]


def copy_item(source: Path, destination: Path) -> None:
    if source.is_dir():
        shutil.copytree(source, destination)
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def write_windows_launcher(path: Path) -> None:
    """Write an optional CLI launcher; API consumers may invoke the binary with NSISDIR."""
    path.write_text(
        "@echo off\r\nsetlocal\r\n"
        'set "NSISDIR=%~dp0..\\..\\common"\r\n'
        '"%~dp0makensis.exe" %*\r\nexit /b %ERRORLEVEL%\r\n',
        encoding="utf-8",
        newline="",
    )


def unix_launcher() -> str:
    """Return an optional CLI launcher that resolves common/ after relocation."""
    return """#!/bin/sh
set -eu
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
NSISDIR=$(CDPATH= cd -- "$SCRIPT_DIR/../../common" && pwd)
export NSISDIR
exec "$SCRIPT_DIR/makensis.bin" "$@"
"""


def stage_windows(config: dict, archive: Path, stage: Path, work: Path) -> None:
    checked_file(archive, config["upstream"]["windowsZip"])
    if stage.exists():
        shutil.rmtree(stage)
    extract = work / "official-windows"
    if extract.exists():
        shutil.rmtree(extract)
    upstream_root = safe_extract_zip(archive, extract)
    common = stage / "common"
    common.mkdir(parents=True)
    for name in COMMON_ITEMS:
        source = upstream_root / name
        if not source.exists():
            raise RuntimeError(f"official ZIP lacks required common item: {name}")
        copy_item(source, common / name)
    host = stage / "hosts" / "win"
    host.mkdir(parents=True)
    for name in ("makensis.exe", "zlib1.dll"):
        source = upstream_root / "Bin" / name
        if not source.is_file():
            raise RuntimeError(f"official ZIP lacks required Windows runtime file: Bin/{name}")
        shutil.copy2(source, host / name)
    write_windows_launcher(host / "makensis.cmd")
    print(f"staged official common data and Windows runtime at {stage}")


def stage_host(config: dict, stage: Path, rid: str, binary: Path, metadata: Path | None) -> None:
    if rid not in config["hosts"] or rid == "win-x64":
        raise RuntimeError(f"unsupported native host RID: {rid}")
    if not binary.is_file():
        raise RuntimeError(f"missing native compiler: {binary}")
    host = stage / "hosts" / config["hosts"][rid]["directory"]
    host.mkdir(parents=True, exist_ok=True)
    output = host / "makensis.bin"
    shutil.copy2(binary, output)
    output.chmod(output.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    launcher = host / "makensis"
    launcher.write_text(unix_launcher(), encoding="utf-8", newline="\n")
    launcher.chmod(0o755)
    if metadata:
        metadata_target = stage / "build" / "hosts" / f"{rid}.json"
        metadata_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(metadata, metadata_target)


def normalized_mode(path: Path, requires_executable: bool = False) -> int:
    # Do not infer Unix intent from os.access: assembly runs on Windows and
    # downloaded CI artifacts commonly lose mode bits.
    return 0o755 if requires_executable else 0o644


def file_record(stage: Path, path: Path, requires_executable: bool = False) -> dict:
    relative = path.relative_to(stage).as_posix()
    mode = normalized_mode(path, requires_executable)
    return {
        "path": relative,
        "sha256": sha256(path),
        "size": path.stat().st_size,
        "unixMode": f"{mode:04o}",
        "requiresExecutable": mode == 0o755,
    }


def generate_manifest(config: dict, stage: Path, provenance: dict | None = None) -> dict:
    for required in (stage / "common" / "Include", stage / "common" / "Plugins", stage / "common" / "Stubs"):
        if not required.is_dir() or not any(required.rglob("*")):
            raise RuntimeError(f"missing or empty required common directory: {required}")
    forbidden_roots = {"scripts", "tests", ".github", "config", "fixtures"}
    for staged_file in (p for p in stage.rglob("*") if p.is_file()):
        relative = staged_file.relative_to(stage)
        if relative.suffix.lower() == ".py" or relative.parts[0] in forbidden_roots:
            raise RuntimeError(f"repository build/test file leaked into toolset: {relative.as_posix()}")
    hosts = []
    for rid, spec in config["hosts"].items():
        for key in ("binary", "convenienceLauncher"):
            if not (stage / spec[key]).is_file():
                raise RuntimeError(f"missing {rid} {key}: {spec[key]}")
        nsisdir = spec.get("requiredEnvironment", {}).get("NSISDIR", {}).get("toolsetRelativePath")
        if nsisdir != "common":
            raise RuntimeError(f"{rid} must declare NSISDIR as toolset-relative common")
        runtime_files = sorted(
            p.relative_to(stage).as_posix()
            for p in (stage / "hosts" / spec["directory"]).rglob("*") if p.is_file()
        )
        if rid != "win-x64":
            metadata_path = stage / "build" / "hosts" / f"{rid}.json"
            if not metadata_path.is_file():
                raise RuntimeError(f"missing build metadata for {rid}")
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if metadata.get("rid") != rid or metadata.get("reportedVersion") != f"v{config['upstreamVersion']}":
                raise RuntimeError(f"version/RID mismatch in build metadata for {rid}")
            if metadata.get("sha256") != sha256(stage / spec["binary"]):
                raise RuntimeError(f"binary hash does not match build metadata for {rid}")
        hosts.append({"rid": rid, **spec, "runtimeFiles": runtime_files})
    executable_paths = {
        spec[key]
        for spec in config["hosts"].values() if spec["unixExecutable"]
        for key in ("convenienceLauncher", "binary")
    }
    files = [
        file_record(stage, p, p.relative_to(stage).as_posix() in executable_paths)
        for p in sorted(stage.rglob("*")) if p.is_file() and p.name != "toolset-manifest.json"
    ]
    manifest = {
        "schemaVersion": 1,
        "toolsetVersion": config["toolsetVersion"],
        "upstreamVersion": config["upstreamVersion"],
        "sourceDateEpoch": config["sourceDateEpoch"],
        "upstream": config["upstream"],
        "commonRoot": "common",
        "hosts": hosts,
        "files": files,
        "invocationPolicy": "Resolve the selected host binary and requiredEnvironment paths against the toolset root. Convenience launchers are optional shell-oriented helpers.",
        "executablePermissionPolicy": "After ZIP extraction, chmod every file whose requiresExecutable is true to its unixMode before executing it.",
    }
    if provenance is not None:
        manifest["provenance"] = provenance
    target = stage / "toolset-manifest.json"
    target.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return manifest


def verify_manifest(stage: Path, repair_modes: bool = False) -> dict:
    path = stage / "toolset-manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    declared = {record["path"] for record in manifest["files"]}
    actual = {p.relative_to(stage).as_posix() for p in stage.rglob("*") if p.is_file() and p != path}
    if actual != declared:
        raise RuntimeError(f"manifest file set mismatch; missing={sorted(declared-actual)}, extra={sorted(actual-declared)}")
    for record in manifest["files"]:
        file_path = stage / PurePosixPath(record["path"])
        if file_path.stat().st_size != record["size"] or sha256(file_path) != record["sha256"]:
            raise RuntimeError(f"file verification failed: {record['path']}")
        if repair_modes and record["requiresExecutable"]:
            file_path.chmod(int(record["unixMode"], 8))
    for host in manifest["hosts"]:
        if not host["binary"].startswith(f"hosts/{host['directory']}/"):
            raise RuntimeError(f"invalid binary layout for {host['rid']}")
        if not host["convenienceLauncher"].startswith(f"hosts/{host['directory']}/"):
            raise RuntimeError(f"invalid launcher layout for {host['rid']}")
        if host.get("requiredEnvironment", {}).get("NSISDIR", {}).get("toolsetRelativePath") != "common":
            raise RuntimeError(f"invalid NSISDIR contract for {host['rid']}")
    print(f"verified {len(actual)} files for {manifest['toolsetVersion']}")
    return manifest


def deterministic_zip(stage: Path, destination: Path, epoch: int) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    timestamp = time.gmtime(max(epoch, 315532800))[:6]
    manifest_path = stage / "toolset-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    modes = {record["path"]: int(record["unixMode"], 8) for record in manifest["files"]}
    modes["toolset-manifest.json"] = 0o644
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for path in sorted(p for p in stage.rglob("*") if p.is_file()):
            relative = path.relative_to(stage).as_posix()
            info = zipfile.ZipInfo(relative, timestamp)
            info.create_system = 3
            info.external_attr = (modes[relative] & 0xFFFF) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            with path.open("rb") as source:
                bundle.writestr(info, source.read(), compresslevel=9)


def package(config: dict, stage: Path, dist: Path) -> None:
    verify_manifest(stage)
    name = f"nsis-toolset-{config['toolsetVersion']}.zip"
    archive = dist / name
    deterministic_zip(stage, archive, config["sourceDateEpoch"])
    checksum = sha256(archive)
    (dist / f"{name}.sha256").write_text(f"{checksum}  {name}\n", encoding="ascii", newline="\n")
    shutil.copy2(stage / "toolset-manifest.json", dist / "toolset-manifest.json")
    print(f"created {archive} ({checksum})")


def verify_zip(archive: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    safe_extract_zip_flat(archive, destination)
    verify_manifest(destination, repair_modes=True)


def safe_extract_zip_flat(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True)
    with zipfile.ZipFile(archive) as bundle:
        for item in bundle.infolist():
            relative = PurePosixPath(item.filename)
            if relative.is_absolute() or ".." in relative.parts:
                raise RuntimeError(f"unsafe ZIP member: {item.filename}")
        bundle.extractall(destination)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("download"); p.add_argument("--cache", type=Path, required=True)
    p = commands.add_parser("stage-windows"); p.add_argument("--archive", type=Path, required=True); p.add_argument("--stage", type=Path, required=True); p.add_argument("--work", type=Path, required=True)
    p = commands.add_parser("stage-host"); p.add_argument("--stage", type=Path, required=True); p.add_argument("--rid", required=True); p.add_argument("--binary", type=Path, required=True); p.add_argument("--metadata", type=Path)
    p = commands.add_parser("manifest"); p.add_argument("--stage", type=Path, required=True); p.add_argument("--provenance", type=Path)
    p = commands.add_parser("verify"); p.add_argument("--stage", type=Path, required=True); p.add_argument("--repair-modes", action="store_true")
    p = commands.add_parser("package"); p.add_argument("--stage", type=Path, required=True); p.add_argument("--dist", type=Path, required=True)
    p = commands.add_parser("verify-zip"); p.add_argument("--archive", type=Path, required=True); p.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    config = load_config(args.config)
    if args.command == "download": download(config, args.cache)
    elif args.command == "stage-windows": stage_windows(config, args.archive, args.stage, args.work)
    elif args.command == "stage-host": stage_host(config, args.stage, args.rid, args.binary, args.metadata)
    elif args.command == "manifest":
        provenance = json.loads(args.provenance.read_text(encoding="utf-8")) if args.provenance else None
        generate_manifest(config, args.stage, provenance)
    elif args.command == "verify": verify_manifest(args.stage, args.repair_modes)
    elif args.command == "package": package(config, args.stage, args.dist)
    elif args.command == "verify-zip": verify_zip(args.archive, args.destination)


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)
