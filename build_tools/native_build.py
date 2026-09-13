"""Build reproducible native NSIS compiler binaries."""

from __future__ import annotations

import os
import shutil
import sys
import tarfile
from pathlib import Path

from . import configuration, linux_build, native_audit, upstream
from .ci_support import recreate, run

SUPPORTED_RIDS = {"linux-x64", "linux-arm64", "osx-x64", "osx-arm64"}


def safe_extract_source(archive: Path, destination: Path) -> Path:
    recreate(destination)
    with tarfile.open(archive, "r:*") as bundle:
        roots: set[str] = set()
        for member in bundle.getmembers():
            relative = upstream.safe_archive_path(member.name)
            roots.add(relative.parts[0])
        if len(roots) != 1:
            raise RuntimeError(f"expected one source archive root, found {len(roots)}")
        bundle.extractall(destination, filter="data")
    source = destination / next(iter(roots))
    if not source.is_dir():
        raise RuntimeError("source archive root is not a directory")
    return source


def _install_build_requirements() -> None:
    run([sys.executable, "-m", "pip", "install", "--require-hashes", "-r", configuration.ROOT / "requirements-build.txt"])


def build_host(config: dict, config_path: Path, upstream_config: Path, toolset_version: str, cache: Path, data_root: Path, rid: str, artifacts: Path) -> None:
    """Build one native host locally or in its pinned Linux container."""
    if rid not in SUPPORTED_RIDS:
        raise RuntimeError(f"unsupported native host RID: {rid}")
    if rid.startswith("linux-"):
        return linux_build.run_in_container(config_path, upstream_config, toolset_version, cache, data_root, rid, artifacts)
    _install_build_requirements()
    build_reproducibly_from_cache(config, cache, data_root, rid, artifacts)


def build_reproducibly_from_cache(config: dict, cache: Path, data_root: Path, rid: str, artifacts: Path) -> None:
    if rid.startswith("linux-"):
        linux_build.prepare_container()
    source = cache / config["upstream"]["sourceArchive"]["fileName"]
    build_reproducibly(config, source, data_root, rid, artifacts / "native-1", artifacts / "native-2", artifacts / "native-work")


def _version_components(version: str) -> list[str]:
    components = version.split(".")
    if not 2 <= len(components) <= 4 or not all(item.isdigit() for item in components):
        raise RuntimeError(f"unsupported NSIS numeric version: {version}")
    return components + ["0"] * (4 - len(components))


def _build_environment(config: dict, data_root: Path, rid: str) -> tuple[dict[str, str], list[str]]:
    environment = os.environ.copy()
    # makensis initializes its default compressor and loads Stubs/uninst before
    # it handles -VERSION, so even the version probe requires a complete data
    # root when NSIS_CONFIG_CONST_DATA_PATH is disabled.
    environment["NSISDIR"] = str(data_root)
    environment["SOURCE_DATE_EPOCH"] = str(config["sourceDateEpoch"])
    if rid.startswith("linux-"):
        return environment, [
            f"CC={environment.get('CC', 'gcc')}",
            f"CXX={environment.get('CXX', 'g++')}",
            "APPEND_LINKFLAGS=-static-libgcc -static-libstdc++",
        ]

    deployment_target = "10.13" if rid == "osx-x64" else "11.0"
    environment["MACOSX_DEPLOYMENT_TARGET"] = deployment_target
    return environment, [
        f"APPEND_CCFLAGS=-mmacosx-version-min={deployment_target}",
        f"APPEND_LINKFLAGS=-mmacosx-version-min={deployment_target}",
    ]


def _scons_command(config: dict, source: Path, install: Path, platform_options: list[str]) -> list[str | Path]:
    version = config["upstreamVersion"]
    components = _version_components(version)
    return [
        sys.executable,
        "-m",
        "SCons",
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
        *platform_options,
        "install-compiler",
    ]


def build_compiler(config: dict, archive: Path, data_root: Path, output: Path, rid: str, work: Path) -> None:
    """Build and audit one compiler binary."""
    if rid not in SUPPORTED_RIDS:
        raise RuntimeError(f"unsupported RID: {rid}")
    upstream.checked_file(archive, config["upstream"]["sourceArchive"])
    recreate(work)
    recreate(output)
    source = safe_extract_source(archive, work / "src")
    data_root = data_root.resolve()
    if not (data_root / "Stubs/uninst").is_file():
        raise RuntimeError(f"NSIS data root does not contain Stubs/uninst: {data_root}")

    install = (work / "install").resolve()
    install.mkdir()
    environment, platform_options = _build_environment(config, data_root, rid)
    run(_scons_command(config, source, install, platform_options), env=environment)

    binary = (output / "makensis").resolve()
    shutil.copy2(install / "makensis", binary)
    binary.chmod(0o755)
    native_audit.audit_compiler(config, rid, binary, work, output, environment)


def build_reproducibly(config: dict, archive: Path, data_root: Path, rid: str, first: Path, second: Path, work: Path) -> None:
    """Build twice and require byte-identical compiler binaries."""
    build_compiler(config, archive, data_root, first, rid, work / f"{rid}-1")
    build_compiler(config, archive, data_root, second, rid, work / f"{rid}-2")
    if (first / "makensis").read_bytes() != (second / "makensis").read_bytes():
        raise RuntimeError(f"repeated {rid} builds produced different compiler bytes")
    print(f"repeated {rid} builds are byte-identical")
