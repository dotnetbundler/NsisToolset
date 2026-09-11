#!/usr/bin/env python3
"""Cross-platform CI orchestration; the workflow only selects runners and moves artifacts."""

from __future__ import annotations

import argparse
import os
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path, PurePosixPath

import host_metadata
import provenance
import toolset


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "toolset.json"


class Arguments(argparse.Namespace):
    config: Path
    upstream_config: Path | None
    toolset_version: str | None
    command: str
    archive: Path
    stage: Path
    work: Path
    fixture: Path
    smoke: Path
    rid: str
    first: Path
    second: Path
    binary: Path
    metadata: Path
    hosts: Path
    artifacts: Path
    source_commit: str
    destination: Path
    installers: Path
    expected_count: int
    dist: Path


def run(command: list[str | Path], *, cwd: Path | None = None, env: dict[str, str] | None = None,
        capture: bool = False, check: bool = True) -> subprocess.CompletedProcess[str]:
    normalized = [str(item) for item in command]
    print(f"+ {shlex.join(normalized)}", flush=True)
    return subprocess.run(
        normalized,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=capture,
        check=check,
    )


def recreate(directory: Path) -> None:
    if directory.exists():
        shutil.rmtree(directory)
    directory.mkdir(parents=True)


def require_version(command: list[str | Path], expected: str, *, cwd: Path | None = None,
                    env: dict[str, str] | None = None) -> None:
    result = run(command, cwd=cwd, env=env, capture=True)
    actual = result.stdout.strip()
    if actual != f"v{expected}":
        raise RuntimeError(f"unexpected compiler version: {actual!r}")


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
        "scons", "-C", source, "-j2", f"VERSION={version}",
        f"VER_MAJOR={components[0]}", f"VER_MINOR={components[1]}",
        f"VER_REVISION={components[2]}", f"VER_BUILD={components[3]}",
        f"SOURCE_DATE_EPOCH={config['sourceDateEpoch']}",
        "NSIS_CONFIG_CONST_DATA_PATH=no", f"PREFIX={install}",
        "SKIPSTUBS=all", "SKIPPLUGINS=all", "SKIPUTILS=all",
        "SKIPMISC=all", "SKIPDOC=all",
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
    host_metadata.write_metadata(
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


def windows_stage_and_smoke(config: dict, archive: Path, stage: Path, work: Path,
                            fixture: Path, smoke: Path) -> None:
    toolset.stage_windows(config, archive, stage, work)
    environment = os.environ.copy()
    environment["NSISDIR"] = str((stage / "common").resolve())
    require_version([stage / "hosts/win-x86/makensis.exe", "-VERSION"], config["upstreamVersion"], env=environment)
    require_version(["cmd.exe", "/d", "/c", stage / "makensis.cmd", "-VERSION"], config["upstreamVersion"], env=environment)
    recreate(smoke)
    shutil.copy2(fixture, smoke / fixture.name)
    run([stage.resolve() / "hosts/win-x86/makensis.exe", fixture.name], cwd=smoke, env=environment)
    if not (smoke / "smoke-installer.exe").is_file():
        raise RuntimeError("Windows compiler smoke test did not produce an installer")


def native_build_twice(config: dict, archive: Path, rid: str, first: Path, second: Path) -> None:
    temporary = Path(os.environ.get("RUNNER_TEMP", tempfile.gettempdir()))
    build_native(config, archive, first, rid, temporary / f"nsis-build-{rid}-1")
    build_native(config, archive, second, rid, temporary / f"nsis-build-{rid}-2")
    if first.joinpath("makensis").read_bytes() != second.joinpath("makensis").read_bytes():
        raise RuntimeError(f"repeated {rid} builds produced different compiler bytes")
    print(f"repeated {rid} builds are byte-identical")


def native_smoke(config: dict, archive: Path, rid: str, binary: Path, metadata: Path,
                 stage: Path, work: Path, fixture: Path, smoke: Path) -> None:
    toolset.stage_windows(config, archive, stage, work)
    toolset.stage_host(config, stage, rid, binary, metadata)
    recreate(smoke)
    shutil.copy2(fixture, smoke / fixture.name)
    environment = os.environ.copy()
    environment["NSISDIR"] = str((stage / "common").resolve())
    direct = (stage / config["hosts"][rid]["binary"]).resolve()
    run([direct, fixture.name], cwd=smoke, env=environment)
    require_version([stage.resolve() / "makensis", "-VERSION"], config["upstreamVersion"], cwd=smoke, env=environment)
    if not (smoke / "smoke-installer.exe").is_file():
        raise RuntimeError(f"{rid} smoke test did not produce an installer")


def assemble(config: dict, stage: Path, hosts: Path, artifacts: Path, source_commit: str) -> None:
    for rid in ("linux-x64", "linux-arm64", "osx-x64", "osx-arm64"):
        root = hosts / f"host-{rid}"
        toolset.stage_host(config, stage, rid, root / "makensis", root / "build-metadata.json")
    provenance_path = artifacts / "build-provenance.json"
    provenance.write_provenance(hosts, config["upstreamVersion"], provenance_path)
    toolset.write_build_record(config, stage, source_commit)
    toolset.write_source_record(config, stage / "SOURCE-RECORD.md")
    toolset.generate_manifest(config, stage)
    toolset.verify_manifest(stage, repair_modes=True)

    dist = artifacts / "dist"
    repeat = artifacts / "repeat"
    recreate(dist)
    recreate(repeat)
    toolset.package(config, stage, dist)
    toolset.package(config, stage, repeat)
    name = f"nsis-toolset-{config['toolsetVersion']}.zip"
    if (dist / name).read_bytes() != (repeat / name).read_bytes():
        raise RuntimeError("repeated packaging produced different ZIP bytes")
    shutil.copy2(provenance_path, dist / "build-provenance.json")
    shutil.copy2(stage / "SOURCE-RECORD.md", dist / "source-record.md")


def relocated_smoke(config: dict, archive: Path, destination: Path, smoke: Path, fixture: Path) -> None:
    toolset.verify_zip(archive, destination)
    recreate(smoke)
    shutil.copy2(fixture, smoke / fixture.name)
    environment = os.environ.copy()
    environment["NSISDIR"] = str((destination / "common").resolve())
    run([destination.resolve() / "hosts/linux-x64/makensis", fixture.name], cwd=smoke, env=environment)
    require_version([destination.resolve() / "makensis", "-VERSION"], config["upstreamVersion"], cwd=smoke, env=environment)
    if not (smoke / "smoke-installer.exe").is_file():
        raise RuntimeError("relocated smoke test did not produce an installer")


def install_uninstall(installers_root: Path, expected_count: int) -> None:
    installers = sorted(installers_root.rglob("smoke-installer.exe"))
    if len(installers) != expected_count:
        raise RuntimeError(f"expected {expected_count} installers, found {len(installers)}")
    install_root = Path(tempfile.gettempdir()) / "NsisToolsetSmoke"
    for installer in installers:
        if install_root.exists():
            shutil.rmtree(install_root)
        run([installer.resolve(), "/S"])
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
    run(["gh", "release", "create", actual_tag, *assets, "--verify-tag",
         "--title", f"NSIS Toolset {config['toolsetVersion']}", "--notes", notes])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--upstream-config", type=Path)
    parser.add_argument("--toolset-version")
    commands = parser.add_subparsers(dest="command", required=True)

    p = commands.add_parser("windows-stage-smoke")
    p.add_argument("--archive", type=Path, required=True); p.add_argument("--stage", type=Path, required=True)
    p.add_argument("--work", type=Path, required=True); p.add_argument("--fixture", type=Path, required=True)
    p.add_argument("--smoke", type=Path, required=True)
    p = commands.add_parser("native-build-twice")
    p.add_argument("--archive", type=Path, required=True); p.add_argument("--rid", required=True)
    p.add_argument("--first", type=Path, required=True); p.add_argument("--second", type=Path, required=True)
    p = commands.add_parser("native-smoke")
    p.add_argument("--archive", type=Path, required=True); p.add_argument("--rid", required=True)
    p.add_argument("--binary", type=Path, required=True); p.add_argument("--metadata", type=Path, required=True)
    p.add_argument("--stage", type=Path, required=True); p.add_argument("--work", type=Path, required=True)
    p.add_argument("--fixture", type=Path, required=True); p.add_argument("--smoke", type=Path, required=True)
    p = commands.add_parser("assemble")
    p.add_argument("--stage", type=Path, required=True); p.add_argument("--hosts", type=Path, required=True)
    p.add_argument("--artifacts", type=Path, required=True); p.add_argument("--source-commit", required=True)
    p = commands.add_parser("relocated-smoke")
    p.add_argument("--archive", type=Path, required=True); p.add_argument("--destination", type=Path, required=True)
    p.add_argument("--smoke", type=Path, required=True); p.add_argument("--fixture", type=Path, required=True)
    p = commands.add_parser("install-uninstall")
    p.add_argument("--installers", type=Path, required=True); p.add_argument("--expected-count", type=int, default=5)
    p = commands.add_parser("publish")
    p.add_argument("--dist", type=Path, required=True)
    args = parser.parse_args(namespace=Arguments())

    if args.command == "install-uninstall":
        install_uninstall(args.installers, args.expected_count)
        return
    if not args.upstream_config or not args.toolset_version:
        parser.error("--upstream-config and --toolset-version are required")
    config = toolset.merged_config(args.config, args.upstream_config, args.toolset_version)
    if args.command == "windows-stage-smoke":
        windows_stage_and_smoke(config, args.archive, args.stage, args.work, args.fixture, args.smoke)
    elif args.command == "native-build-twice":
        native_build_twice(config, args.archive, args.rid, args.first, args.second)
    elif args.command == "native-smoke":
        native_smoke(config, args.archive, args.rid, args.binary, args.metadata, args.stage, args.work, args.fixture, args.smoke)
    elif args.command == "assemble":
        assemble(config, args.stage, args.hosts, args.artifacts, args.source_commit)
    elif args.command == "relocated-smoke":
        relocated_smoke(config, args.archive, args.destination, args.smoke, args.fixture)
    elif args.command == "publish":
        publish(config, args.dist)


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.CalledProcessError, tarfile.TarError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)
