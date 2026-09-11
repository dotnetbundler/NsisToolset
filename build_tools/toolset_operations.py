#!/usr/bin/env python3
"""Reusable download, staging, manifest, and packaging operations."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import stat
import time
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "toolset.json"
DEFAULT_UPSTREAM_DIR = ROOT / "config" / "upstream"
COMMON_ITEMS = ("Contrib", "Include", "Plugins", "Stubs", "nsisconf.nsh", "COPYING")


def load_config(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def merged_config(base_path: Path, upstream_path: Path, toolset_version: str) -> dict:
    base = load_config(base_path)
    upstream = load_config(upstream_path)
    if upstream_path.stem != upstream.get("upstreamVersion"):
        raise RuntimeError(f"upstream config filename/version mismatch: {upstream_path}")
    prefix = f"{upstream['upstreamVersion']}-"
    if not toolset_version.startswith(prefix):
        raise RuntimeError(f"toolset version {toolset_version} does not use upstream {upstream['upstreamVersion']}")
    local_version = toolset_version[len(prefix) :]
    if not re.fullmatch(r"[0-9A-Za-z][0-9A-Za-z.-]*", local_version):
        raise RuntimeError(f"invalid local version label: {local_version}")
    config = {**base, **upstream, "toolsetVersion": toolset_version}
    return config


def resolve_version(version: str, upstream_dir: Path = DEFAULT_UPSTREAM_DIR) -> dict[str, str]:
    if not re.fullmatch(r"v[0-9][0-9A-Za-z.-]*-[0-9A-Za-z][0-9A-Za-z.-]*", version):
        raise RuntimeError("version must have form v<upstream>-<local>, for example v3.12-r1 or v3.12-preview.2")
    candidates = []
    for path in upstream_dir.glob("*.json"):
        upstream_version = path.stem
        prefix = f"v{upstream_version}-"
        if version.startswith(prefix):
            candidates.append((len(upstream_version), upstream_version, path))
    if not candidates:
        raise RuntimeError(f"no registered upstream config matches {version}")
    _, upstream_version, path = max(candidates)
    local_version = version[len(upstream_version) + 2 :]
    upstream = load_config(path)
    if upstream.get("upstreamVersion") != upstream_version:
        raise RuntimeError(f"upstream config filename/version mismatch: {path}")
    try:
        config_output = path.relative_to(ROOT).as_posix()
    except ValueError:
        config_output = path.as_posix()
    return {
        "tag": version,
        "toolsetVersion": version[1:],
        "upstreamVersion": upstream_version,
        "localVersion": local_version,
        "upstreamConfig": config_output,
        "sourceDateEpoch": str(upstream["sourceDateEpoch"]),
        "windowsArchive": upstream["upstream"]["windowsZip"]["fileName"],
        "sourceArchive": upstream["upstream"]["sourceArchive"]["fileName"],
    }


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
    if (
        actual_size != spec["size"]
        or actual_sha1 != expected_sha1
        or actual_sha256 != expected_sha256
    ):
        raise RuntimeError(f"upstream verification failed for {path.name}: size={actual_size}, sha1={actual_sha1}, sha256={actual_sha256}")


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
                with (
                    urllib.request.urlopen(request, timeout=90) as response,
                    temporary.open("wb") as output,
                ):
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


def write_root_launchers(stage: Path) -> None:
    """Write human-facing dispatchers; API consumers invoke manifest binaries directly."""
    windows_path = stage / "makensis.cmd"
    posix_path = stage / "makensis"
    stage.mkdir(parents=True, exist_ok=True)
    windows_path.write_text(
        "@echo off\r\nsetlocal\r\n"
        'set "NSISDIR=%~dp0common"\r\n'
        '"%~dp0hosts\\win-x86\\makensis.exe" %*\r\nexit /b %ERRORLEVEL%\r\n',
        encoding="utf-8",
        newline="",
    )
    posix_path.write_text(
        """#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
OS=$(uname -s)
ARCH=$(uname -m)
case "$OS:$ARCH" in
  Linux:x86_64) RID=linux-x64 ;;
  Linux:aarch64|Linux:arm64) RID=linux-arm64 ;;
  Darwin:x86_64) RID=osx-x64 ;;
  Darwin:arm64) RID=osx-arm64 ;;
  *) echo "unsupported host: $OS/$ARCH" >&2; exit 2 ;;
esac
NSISDIR="$ROOT/common"
export NSISDIR
exec "$ROOT/hosts/$RID/makensis" "$@"
""",
        encoding="utf-8",
        newline="\n",
    )
    posix_path.chmod(0o755)


def verify_windows_x86(binary: Path) -> None:
    data = binary.read_bytes()
    if data[:2] != b"MZ" or len(data) < 0x40:
        raise RuntimeError("official Windows compiler is not a PE executable")
    pe_offset = int.from_bytes(data[0x3C:0x40], "little")
    if data[pe_offset : pe_offset + 4] != b"PE\0\0":
        raise RuntimeError("official Windows compiler has an invalid PE header")
    machine = int.from_bytes(data[pe_offset + 4 : pe_offset + 6], "little")
    if machine != 0x014C:
        raise RuntimeError(f"official Windows compiler is not x86 (PE machine 0x{machine:04x})")


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
    host = stage / "hosts" / "win-x86"
    host.mkdir(parents=True)
    for name in ("makensis.exe", "zlib1.dll"):
        source = upstream_root / "Bin" / name
        if not source.is_file():
            raise RuntimeError(f"official ZIP lacks required Windows runtime file: Bin/{name}")
        shutil.copy2(source, host / name)
    verify_windows_x86(host / "makensis.exe")
    write_root_launchers(stage)
    print(f"staged official common data and Windows runtime at {stage}")


def stage_host(config: dict, stage: Path, rid: str, binary: Path, metadata: Path | None) -> None:
    if rid not in config["hosts"] or rid == "win-x86":
        raise RuntimeError(f"unsupported native host RID: {rid}")
    if not binary.is_file():
        raise RuntimeError(f"missing native compiler: {binary}")
    host = stage / "hosts" / config["hosts"][rid]["directory"]
    host.mkdir(parents=True, exist_ok=True)
    output = host / "makensis"
    shutil.copy2(binary, output)
    output.chmod(output.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    if metadata:
        item = json.loads(metadata.read_text(encoding="utf-8"))
        if item.get("rid") != rid or item.get("reportedVersion") != f"v{config['upstreamVersion']}":
            raise RuntimeError(f"version/RID mismatch in build metadata for {rid}")
        if item.get("sha256") != sha256(output):
            raise RuntimeError(f"binary hash does not match build metadata for {rid}")


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


def generate_manifest(config: dict, stage: Path) -> dict:
    for required in (
        stage / "common" / "Include",
        stage / "common" / "Plugins",
        stage / "common" / "Stubs",
    ):
        if not required.is_dir() or not any(required.rglob("*")):
            raise RuntimeError(f"missing or empty required common directory: {required}")
    forbidden_roots = {"scripts", "tests", ".github", "config", "fixtures"}
    for staged_file in (p for p in stage.rglob("*") if p.is_file()):
        relative = staged_file.relative_to(stage)
        if relative.suffix.lower() == ".py" or relative.parts[0] in forbidden_roots:
            raise RuntimeError(f"repository build/test file leaked into toolset: {relative.as_posix()}")
    hosts = []
    for rid, spec in config["hosts"].items():
        if not (stage / spec["binary"]).is_file():
            raise RuntimeError(f"missing {rid} binary: {spec['binary']}")
        nsisdir = spec.get("requiredEnvironment", {}).get("NSISDIR", {}).get("toolsetRelativePath")
        if nsisdir != "common":
            raise RuntimeError(f"{rid} must declare NSISDIR as toolset-relative common")
        runtime_files = sorted(p.relative_to(stage).as_posix() for p in (stage / "hosts" / spec["directory"]).rglob("*") if p.is_file())
        hosts.append({"rid": rid, **spec, "runtimeFiles": runtime_files})
    for launcher in config["launchers"].values():
        if not (stage / launcher).is_file():
            raise RuntimeError(f"missing root launcher: {launcher}")
    executable_paths = {
        spec["binary"] for spec in config["hosts"].values() if spec["unixExecutable"]
    } | {config["launchers"]["posix"]}
    files = [
        file_record(stage, p, p.relative_to(stage).as_posix() in executable_paths)
        for p in sorted(stage.rglob("*"))
        if p.is_file() and p.name != "toolset-manifest.json"
    ]
    manifest = {
        "schemaVersion": 1,
        "toolsetVersion": config["toolsetVersion"],
        "upstreamVersion": config["upstreamVersion"],
        "sourceDateEpoch": config["sourceDateEpoch"],
        "upstream": config["upstream"],
        "commonRoot": "common",
        "hosts": hosts,
        "launchers": config["launchers"],
        "files": files,
        "invocationPolicy": "Programs resolve a host binary and requiredEnvironment against the toolset root. Humans may use the root dispatcher.",
        "executablePermissionPolicy": "After ZIP extraction, chmod every file whose requiresExecutable is true to its unixMode before executing it.",
    }
    target = stage / "toolset-manifest.json"
    target.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return manifest


def verify_manifest(stage: Path, repair_modes: bool = False) -> dict:
    path = stage / "toolset-manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    declared = {record["path"] for record in manifest["files"]}
    actual = {
        p.relative_to(stage).as_posix() for p in stage.rglob("*") if p.is_file() and p != path
    }
    if actual != declared:
        raise RuntimeError(f"manifest file set mismatch; missing={sorted(declared - actual)}, extra={sorted(actual - declared)}")
    for record in manifest["files"]:
        file_path = stage / PurePosixPath(record["path"])
        if file_path.stat().st_size != record["size"] or sha256(file_path) != record["sha256"]:
            raise RuntimeError(f"file verification failed: {record['path']}")
        if repair_modes and record["requiresExecutable"]:
            file_path.chmod(int(record["unixMode"], 8))
    for host in manifest["hosts"]:
        if not host["binary"].startswith(f"hosts/{host['directory']}/"):
            raise RuntimeError(f"invalid binary layout for {host['rid']}")
        if (
            host.get("requiredEnvironment", {}).get("NSISDIR", {}).get("toolsetRelativePath")
            != "common"
        ):
            raise RuntimeError(f"invalid NSISDIR contract for {host['rid']}")
    if manifest.get("launchers") != {"windows": "makensis.cmd", "posix": "makensis"}:
        raise RuntimeError("invalid root launcher contract")
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


def write_build_record(config: dict, stage: Path, source_commit: str) -> dict:
    record = {
        "schemaVersion": 1,
        "toolsetVersion": config["toolsetVersion"],
        "upstreamVersion": config["upstreamVersion"],
        "sourceDateEpoch": config["sourceDateEpoch"],
        "sourceCommit": source_commit,
        "upstream": config["upstream"],
        "nativeBuildPolicy": {
            "patches": [],
            "constDataPath": False,
            "commonDataSource": "verified official Windows ZIP",
        },
    }
    target = stage / "build-record.json"
    target.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return record


def write_source_record(config: dict, target: Path) -> None:
    rows = []
    for spec in config["upstream"].values():
        rows.append(
            f"| `{spec['fileName']}` | <{spec['url']}> | {spec['size']} | "
            f"`{spec['digests']['upstreamPublished']['sha1']}` | "
            f"`{spec['digests']['upstreamPublished']['md5']}` | "
            f"`{spec['digests']['locallyDerived']['sha256']}` |"
        )
    text = f"""# Source record

Toolset version: `{config["toolsetVersion"]}`
Upstream NSIS version: `{config["upstreamVersion"]}`
`SOURCE_DATE_EPOCH`: `{config["sourceDateEpoch"]}`

| Input | Official URL | Bytes | Upstream SHA-1 | Upstream MD5 | Locally derived SHA-256 |
| --- | --- | ---: | --- | --- | --- |
{chr(10).join(rows)}

Downloads are accepted only when byte size, upstream-published SHA-1, and
locally derived SHA-256 all match. MD5 is recorded but is not an acceptance
check.
"""
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8", newline="\n")


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
