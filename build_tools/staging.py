"""Stage common NSIS data and host runtimes."""

from __future__ import annotations

import json
import shutil
import stat
from pathlib import Path

from . import upstream
from .ci_support import recreate

COMMON_ITEMS = ("Contrib", "Include", "Plugins", "Stubs", "nsisconf.nsh", "COPYING")
WINDOWS_RUNTIME_ITEMS = ("makensis.exe", "zlib1.dll")


def _copy_item(source: Path, destination: Path) -> None:
    if source.is_dir():
        shutil.copytree(source, destination)
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def write_root_launchers(stage: Path) -> None:
    """Write launchers that select the current host and configure NSISDIR."""
    windows_path = stage / "makensis.cmd"
    posix_path = stage / "makensis"
    stage.mkdir(parents=True, exist_ok=True)
    windows_path.write_text(r"""@echo off
setlocal
set "NSISDIR=%~dp0common"
"%~dp0hosts\win-x86\makensis.exe" %*
exit /b %ERRORLEVEL%
""", encoding="utf-8", newline="\r\n")
    posix_path.write_text("""#!/bin/sh
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
""", encoding="utf-8", newline="\n")
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


def _extract_windows(config: dict, archive: Path, work: Path, clean: bool) -> Path:
    upstream.checked_file(archive, config["upstream"]["windowsZip"])
    extract = work / "official-windows"
    if clean:
        recreate(extract)
        return upstream.safe_extract_zip(archive, extract)
    roots = [path for path in extract.iterdir() if path.is_dir()] if extract.is_dir() else []
    if len(roots) == 1:
        return roots[0]
    if extract.exists():
        shutil.rmtree(extract)
    return upstream.safe_extract_zip(archive, extract)


def stage_common(config: dict, archive: Path, stage: Path, work: Path) -> None:
    recreate(stage)
    upstream_root = _extract_windows(config, archive, work, clean=True)
    common = stage / "common"
    common.mkdir(parents=True)
    for name in COMMON_ITEMS:
        source = upstream_root / name
        if not source.exists():
            raise RuntimeError(f"official ZIP lacks required common item: {name}")
        _copy_item(source, common / name)
    write_root_launchers(stage)
    print(f"staged official common data and root launchers at {stage}")


def stage_windows_host(config: dict, archive: Path, stage: Path, work: Path) -> None:
    upstream_root = _extract_windows(config, archive, work, clean=False)
    host = stage / "hosts" / "win-x86"
    host.mkdir(parents=True, exist_ok=True)
    for name in WINDOWS_RUNTIME_ITEMS:
        source = upstream_root / "Bin" / name
        if not source.is_file():
            raise RuntimeError(f"official ZIP lacks required Windows runtime file: Bin/{name}")
        shutil.copy2(source, host / name)
    verify_windows_x86(host / "makensis.exe")
    print(f"staged official Windows x86 runtime at {host}")


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
    launcher = stage / "makensis"
    launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    if metadata:
        item = json.loads(metadata.read_text(encoding="utf-8"))
        if item.get("rid") != rid or item.get("reportedVersion") != f"v{config['upstreamVersion']}":
            raise RuntimeError(f"version/RID mismatch in build metadata for {rid}")
        if item.get("sha256") != upstream.sha256(output):
            raise RuntimeError(f"binary hash does not match build metadata for {rid}")
