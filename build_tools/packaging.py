"""Create, verify, and package the final toolset."""

from __future__ import annotations

import json
import shutil
import time
import zipfile
from pathlib import Path, PurePosixPath

from . import upstream

FORBIDDEN_RELEASE_ROOTS = {".github", "build_tools", "config", "fixtures", "tests"}


def normalized_mode(requires_executable: bool = False) -> int:
    return 0o755 if requires_executable else 0o644


def file_record(stage: Path, path: Path, requires_executable: bool = False) -> dict:
    return {
        "path": path.relative_to(stage).as_posix(),
        "sha256": upstream.sha256(path),
        "size": path.stat().st_size,
        "unixMode": f"{normalized_mode(requires_executable):04o}",
        "requiresExecutable": requires_executable,
    }


def generate_manifest(config: dict, stage: Path) -> dict:
    for required in (stage / "common" / "Include", stage / "common" / "Plugins", stage / "common" / "Stubs"):
        if not required.is_dir() or not any(required.rglob("*")):
            raise RuntimeError(f"missing or empty required common directory: {required}")
    for staged_file in (path for path in stage.rglob("*") if path.is_file()):
        relative = staged_file.relative_to(stage)
        if relative.suffix.lower() == ".py" or relative.parts[0] in FORBIDDEN_RELEASE_ROOTS:
            raise RuntimeError(f"repository build/test file leaked into toolset: {relative.as_posix()}")
    hosts = []
    for rid, spec in config["hosts"].items():
        if not (stage / spec["binary"]).is_file():
            raise RuntimeError(f"missing {rid} binary: {spec['binary']}")
        nsisdir = spec.get("requiredEnvironment", {}).get("NSISDIR", {}).get("toolsetRelativePath")
        if nsisdir != "common":
            raise RuntimeError(f"{rid} must declare NSISDIR as toolset-relative common")
        runtime_files = sorted(path.relative_to(stage).as_posix() for path in (stage / "hosts" / spec["directory"]).rglob("*") if path.is_file())
        hosts.append({"rid": rid, **spec, "runtimeFiles": runtime_files})
    for launcher in config["launchers"].values():
        if not (stage / launcher).is_file():
            raise RuntimeError(f"missing root launcher: {launcher}")
    executable_paths = {spec["binary"] for spec in config["hosts"].values() if spec["unixExecutable"]} | {config["launchers"]["posix"]}
    files = [file_record(stage, path, path.relative_to(stage).as_posix() in executable_paths) for path in sorted(stage.rglob("*")) if path.is_file() and path.name != "toolset-manifest.json"]
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
    actual = {item.relative_to(stage).as_posix() for item in stage.rglob("*") if item.is_file() and item != path}
    if actual != declared:
        raise RuntimeError(f"manifest file set mismatch; missing={sorted(declared - actual)}, extra={sorted(actual - declared)}")
    for record in manifest["files"]:
        file_path = stage / PurePosixPath(record["path"])
        if file_path.stat().st_size != record["size"] or upstream.sha256(file_path) != record["sha256"]:
            raise RuntimeError(f"file verification failed: {record['path']}")
        if repair_modes and record["requiresExecutable"]:
            file_path.chmod(int(record["unixMode"], 8))
    for host in manifest["hosts"]:
        if not host["binary"].startswith(f"hosts/{host['directory']}/"):
            raise RuntimeError(f"invalid binary layout for {host['rid']}")
        nsisdir = host.get("requiredEnvironment", {}).get("NSISDIR", {}).get("toolsetRelativePath")
        if nsisdir != "common":
            raise RuntimeError(f"invalid NSISDIR contract for {host['rid']}")
    if manifest.get("launchers") != {"windows": "makensis.cmd", "posix": "makensis"}:
        raise RuntimeError("invalid root launcher contract")
    print(f"verified {len(actual)} files for {manifest['toolsetVersion']}")
    return manifest


def deterministic_zip(stage: Path, destination: Path, epoch: int) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    timestamp = time.gmtime(max(epoch, 315532800))[:6]
    manifest = json.loads((stage / "toolset-manifest.json").read_text(encoding="utf-8"))
    modes = {record["path"]: int(record["unixMode"], 8) for record in manifest["files"]}
    modes["toolset-manifest.json"] = 0o644
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for path in sorted(item for item in stage.rglob("*") if item.is_file()):
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
    checksum = upstream.sha256(archive)
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
        "nativeBuildPolicy": {"patches": [], "constDataPath": False, "commonDataSource": "verified official Windows ZIP"},
    }
    target = stage / "build-record.json"
    target.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return record


def write_source_record(config: dict, target: Path) -> None:
    rows = []
    for spec in config["upstream"].values():
        rows.append(f"| `{spec['fileName']}` | <{spec['url']}> | {spec['size']} | `{spec['digests']['upstreamPublished']['sha1']}` | `{spec['digests']['upstreamPublished']['md5']}` | `{spec['digests']['locallyDerived']['sha256']}` |")
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


def verify_zip(archive: Path, destination: Path) -> dict:
    if destination.exists():
        shutil.rmtree(destination)
    upstream.safe_extract_zip_flat(archive, destination)
    return verify_manifest(destination, repair_modes=True)
