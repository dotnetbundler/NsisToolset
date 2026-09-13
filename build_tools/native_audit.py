"""Audit built NSIS compilers and record their build metadata."""

from __future__ import annotations

import hashlib
import json
import platform
import re
import sys
from pathlib import Path

from . import configuration
from .ci_support import run


def _read_report(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace").strip()


def _command_version(command: list[str], environment: dict[str, str]) -> str:
    return run(command, env=environment, capture=True).stdout.splitlines()[0]


def _write_metadata(config: dict, rid: str, binary: Path, output: Path, environment: dict[str, str]) -> None:
    data = binary.read_bytes()
    metadata = {
        "rid": rid,
        "sha256": hashlib.sha256(data).hexdigest(),
        "size": len(data),
        "reportedVersion": _read_report(output / "version.txt"),
        "binaryFormat": _read_report(output / "file.txt"),
        "dynamicDependencies": _read_report(output / "dependencies.txt").splitlines(),
        "runner": {
            "os": platform.platform(),
            "machine": platform.machine(),
            "image": environment.get("ImageOS"),
            "imageVersion": environment.get("ImageVersion"),
        },
        "toolchain": {
            "compiler": _command_version([environment.get("CXX", "c++"), "--version"], environment),
            "scons": _command_version([sys.executable, "-m", "SCons", "--version"], environment),
        },
        "buildParameters": {
            "version": config["upstreamVersion"],
            "NSIS_CONFIG_CONST_DATA_PATH": "no",
            "SOURCE_DATE_EPOCH": str(config["sourceDateEpoch"]),
            "linuxLibc": "glibc" if rid.startswith("linux-") else None,
            "linuxGlibcBaseline": "2.17" if rid.startswith("linux-") else None,
            "macosDeploymentTarget": environment.get("MACOSX_DEPLOYMENT_TARGET"),
        },
        "patches": [],
    }
    (output / "build-metadata.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def _version_tuple(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split("."))


def _verify_cp936(binary: Path, work: Path, environment: dict[str, str]) -> None:
    """Exercise glibc iconv/gconv by loading NSIS's CP936 language table."""
    fixture = configuration.ROOT / "fixtures" / "cp936-codepage-smoke.nsi"
    output = (work / "cp936-codepage-smoke.exe").resolve()
    run([binary, fixture.resolve(), f"-XOutFile {output}"], cwd=work, env=environment)
    if not output.is_file():
        raise RuntimeError("Linux makensis did not compile the CP936 code-page smoke fixture")


def _audit_linux(binary: Path, work: Path, environment: dict[str, str], rid: str, output: Path) -> str:
    notes = run(["readelf", "--notes", binary], capture=True).stdout
    (output / "elf-notes.txt").write_text(notes, encoding="utf-8", newline="\n")

    dynamic = run(["readelf", "--dynamic", binary], capture=True).stdout
    dependencies = set(re.findall(r"\(NEEDED\).*Shared library: \[([^]]+)]", dynamic))
    loader = "ld-linux-x86-64.so.2" if rid == "linux-x64" else "ld-linux-aarch64.so.1"
    allowed = {loader, "libc.so.6", "libdl.so.2", "libm.so.6", "libpthread.so.0", "librt.so.1", "libz.so.1"}
    if not dependencies or dependencies - allowed:
        raise RuntimeError(f"unexpected Linux dynamic dependencies: {sorted(dependencies)}")

    headers = run(["readelf", "--program-headers", binary], capture=True).stdout
    if not re.search(r"^\s*INTERP\s", headers, flags=re.MULTILINE):
        raise RuntimeError("Linux makensis must have a glibc dynamic interpreter")

    version_report = run(["readelf", "--version-info", binary], capture=True).stdout
    glibc_versions = set(re.findall(r"\bGLIBC_(\d+(?:\.\d+)+)\b", version_report))
    if not glibc_versions or max(map(_version_tuple, glibc_versions)) > (2, 17):
        raise RuntimeError(f"Linux makensis exceeds the GLIBC_2.17 baseline: {sorted(glibc_versions, key=_version_tuple)}")
    if re.search(r"\b(?:GLIBCXX|CXXABI)_", version_report):
        raise RuntimeError("Linux makensis must statically link the C++ runtime")

    dependency_report = run(["ldd", binary], capture=True, check=False)
    result = dependency_report.stdout + dependency_report.stderr
    if "not found" in result:
        raise RuntimeError(f"Linux makensis has unresolved dependencies:\n{result}")
    _verify_cp936(binary, work, environment)
    return result


def _audit_macos(binary: Path) -> str:
    result = run(["otool", "-L", binary], capture=True).stdout
    for line in result.splitlines()[1:]:
        dependency = line.strip()
        if dependency and not dependency.startswith(("/usr/lib/", "/System/Library/")):
            raise RuntimeError(f"macOS makensis has a non-system dependency: {dependency}")
    return result


def audit_compiler(config: dict, rid: str, binary: Path, work: Path, output: Path, environment: dict[str, str]) -> None:
    """Check version, format, platform dependencies, and build metadata."""
    version = run([binary, "-VERSION"], env=environment, capture=True).stdout
    (output / "version.txt").write_text(version, encoding="utf-8", newline="\n")
    if version.strip() != f"v{config['upstreamVersion']}":
        raise RuntimeError(f"built compiler reported {version.strip()!r}")

    file_report = run(["file", binary], capture=True).stdout
    (output / "file.txt").write_text(file_report, encoding="utf-8", newline="\n")
    dependencies = _audit_linux(binary, work, environment, rid, output) if rid.startswith("linux-") else _audit_macos(binary)
    (output / "dependencies.txt").write_text(dependencies, encoding="utf-8", newline="\n")
    _write_metadata(config, rid, binary, output, environment)
