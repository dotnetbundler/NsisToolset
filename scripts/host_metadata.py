#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import platform
import subprocess
from pathlib import Path


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace").strip()


def write_metadata(*, rid: str, binary: Path, version_file: Path, file_report: Path,
                   dependencies: Path, upstream_version: str, source_date_epoch: str,
                   output: Path, environment: dict[str, str] | None = None) -> dict:
    environment = environment or os.environ.copy()
    data = binary.read_bytes()
    metadata = {
        "rid": rid,
        "sha256": hashlib.sha256(data).hexdigest(),
        "size": len(data),
        "reportedVersion": text(version_file),
        "binaryFormat": text(file_report),
        "dynamicDependencies": text(dependencies).splitlines(),
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rid", required=True)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--version-file", type=Path, required=True)
    parser.add_argument("--file-report", type=Path, required=True)
    parser.add_argument("--dependencies", type=Path, required=True)
    parser.add_argument("--upstream-version", required=True)
    parser.add_argument("--source-date-epoch", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    write_metadata(**vars(args))


if __name__ == "__main__":
    main()
