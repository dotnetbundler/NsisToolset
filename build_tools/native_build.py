"""Build and audit native NSIS compiler binaries."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

from . import toolset_operations as toolset
from .ci_support import recreate, run


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace").strip()


def write_metadata(*, rid: str, binary: Path, version_file: Path, file_report: Path, dependencies: Path, upstream_version: str, source_date_epoch: str, output: Path, environment: dict[str, str]) -> dict:
    data = binary.read_bytes()
    metadata = {
        "rid": rid,
        "sha256": hashlib.sha256(data).hexdigest(),
        "size": len(data),
        "reportedVersion": read_text(version_file),
        "binaryFormat": read_text(file_report),
        "dynamicDependencies": read_text(dependencies).splitlines(),
        "runner": {
            "os": platform.platform(),
            "machine": platform.machine(),
            "image": environment.get("ImageOS"),
            "imageVersion": environment.get("ImageVersion"),
        },
        "toolchain": {
            "compiler": subprocess.run([environment.get("CXX", "c++"), "--version"], text=True, capture_output=True, env=environment, check=True).stdout.splitlines()[0],
            "scons": subprocess.run(["scons", "--version"], text=True, capture_output=True, env=environment, check=True).stdout.splitlines()[0],
        },
        "buildParameters": {
            "version": upstream_version,
            "NSIS_CONFIG_CONST_DATA_PATH": "no",
            "SOURCE_DATE_EPOCH": source_date_epoch,
            "linuxStaticLink": rid.startswith("linux-"),
            "macosDeploymentTarget": environment.get("MACOSX_DEPLOYMENT_TARGET"),
        },
        "patches": [],
    }
    output.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return metadata


def safe_extract_source(archive: Path, destination: Path) -> Path:
    recreate(destination)
    with tarfile.open(archive, "r:bz2") as bundle:
        roots: set[str] = set()
        for member in bundle.getmembers():
            relative = PurePosixPath(member.name)
            if relative.is_absolute() or ".." in relative.parts or not relative.parts:
                raise RuntimeError(f"unsafe source archive member: {member.name}")
            roots.add(relative.parts[0])
        if len(roots) != 1:
            raise RuntimeError(f"expected one source archive root, found {len(roots)}")
        bundle.extractall(destination, filter="data")
    source = destination / next(iter(roots))
    if not source.is_dir():
        raise RuntimeError("source archive root is not a directory")
    return source


def build_native(config: dict, archive: Path, output: Path, rid: str, work: Path) -> None:
    if rid not in {"linux-x64", "linux-arm64", "osx-x64", "osx-arm64"}:
        raise RuntimeError(f"unsupported RID: {rid}")
    toolset.checked_file(archive, config["upstream"]["sourceArchive"])
    recreate(work)
    recreate(output)
    source = safe_extract_source(archive, work / "src")
    install = work / "install"
    install.mkdir()

    version = config["upstreamVersion"]
    components = version.split(".")
    if not 2 <= len(components) <= 4 or not all(item.isdigit() for item in components):
        raise RuntimeError(f"unsupported NSIS numeric version: {version}")
    components += ["0"] * (4 - len(components))
    environment = os.environ.copy()
    environment["SOURCE_DATE_EPOCH"] = str(config["sourceDateEpoch"])
    command = [
        "scons",
        "-C",
        source,
        "-j2",
        f"VERSION={version}",
        f"VER_MAJOR={components[0]}",
        f"VER_MINOR={components[1]}",
        f"VER_REVISION={components[2]}",
        f"VER_BUILD={components[3]}",
        f"SOURCE_DATE_EPOCH={config['sourceDateEpoch']}",
        "NSIS_CONFIG_CONST_DATA_PATH=no",
        f"PREFIX={install}",
        "SKIPSTUBS=all",
        "SKIPPLUGINS=all",
        "SKIPUTILS=all",
        "SKIPMISC=all",
        "SKIPDOC=all",
    ]
    if rid.startswith("linux-"):
        command.append("APPEND_LINKFLAGS=-static")
    elif rid == "osx-x64":
        environment["MACOSX_DEPLOYMENT_TARGET"] = "10.13"
        command.extend(["APPEND_CCFLAGS=-mmacosx-version-min=10.13", "APPEND_LINKFLAGS=-mmacosx-version-min=10.13"])
    else:
        environment["MACOSX_DEPLOYMENT_TARGET"] = "11.0"
        command.extend(["APPEND_CCFLAGS=-mmacosx-version-min=11.0", "APPEND_LINKFLAGS=-mmacosx-version-min=11.0"])
    command.append("install-compiler")
    run(command, env=environment)

    binary = output / "makensis"
    shutil.copy2(install / "makensis", binary)
    binary.chmod(0o755)
    version_result = run([binary, "-VERSION"], capture=True)
    (output / "version.txt").write_text(version_result.stdout, encoding="utf-8", newline="\n")
    if version_result.stdout.strip() != f"v{version}":
        raise RuntimeError(f"built compiler reported {version_result.stdout.strip()!r}")

    file_result = run(["file", binary], capture=True)
    (output / "file.txt").write_text(file_result.stdout, encoding="utf-8", newline="\n")
    if rid.startswith("linux-"):
        notes = run(["readelf", "--notes", binary], capture=True).stdout
        (output / "elf-notes.txt").write_text(notes, encoding="utf-8", newline="\n")
        dependency_result = run(["ldd", binary], capture=True, check=False)
        dependencies = dependency_result.stdout + dependency_result.stderr
        if not re.search(r"not a dynamic executable|statically linked", dependencies):
            raise RuntimeError("Linux makensis must be fully static")
        expected_abi = "3.2.0" if rid == "linux-x64" else "3.7.0"
        if f"ABI: {expected_abi}" not in notes:
            raise RuntimeError(f"ELF notes do not prove Linux baseline {expected_abi}")
    else:
        dependencies = run(["otool", "-L", binary], capture=True).stdout
        for line in dependencies.splitlines()[1:]:
            dependency = line.strip()
            if dependency and not dependency.startswith(("/usr/lib/", "/System/Library/")):
                raise RuntimeError(f"macOS makensis has a non-system dependency: {dependency}")
    (output / "dependencies.txt").write_text(dependencies, encoding="utf-8", newline="\n")
    write_metadata(
        rid=rid,
        binary=binary,
        version_file=output / "version.txt",
        file_report=output / "file.txt",
        dependencies=output / "dependencies.txt",
        upstream_version=version,
        source_date_epoch=str(config["sourceDateEpoch"]),
        output=output / "build-metadata.json",
        environment=environment,
    )


def build_twice(config: dict, archive: Path, rid: str, first: Path, second: Path) -> None:
    temporary = Path(os.environ.get("RUNNER_TEMP", tempfile.gettempdir()))
    build_native(config, archive, first, rid, temporary / f"nsis-build-{rid}-1")
    build_native(config, archive, second, rid, temporary / f"nsis-build-{rid}-2")
    if (first / "makensis").read_bytes() != (second / "makensis").read_bytes():
        raise RuntimeError(f"repeated {rid} builds produced different compiler bytes")
    print(f"repeated {rid} builds are byte-identical")
