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

data = args.binary.read_bytes()
metadata = {
    "rid": args.rid,
    "sha256": hashlib.sha256(data).hexdigest(),
    "size": len(data),
    "reportedVersion": text(args.version_file),
    "binaryFormat": text(args.file_report),
    "dynamicDependencies": text(args.dependencies).splitlines(),
    "runner": {
        "os": platform.platform(),
        "machine": platform.machine(),
        "image": os.environ.get("ImageOS"),
        "imageVersion": os.environ.get("ImageVersion"),
    },
    "toolchain": {
        "compiler": subprocess.run([os.environ.get("CXX", "c++"), "--version"], text=True, capture_output=True).stdout.splitlines()[0],
        "scons": subprocess.run(["scons", "--version"], text=True, capture_output=True).stdout.splitlines()[0],
    },
    "buildParameters": {
        "version": args.upstream_version,
        "NSIS_CONFIG_CONST_DATA_PATH": "no",
        "SOURCE_DATE_EPOCH": args.source_date_epoch,
        "linuxStaticLink": args.rid.startswith("linux-"),
        "macosDeploymentTarget": os.environ.get("MACOSX_DEPLOYMENT_TARGET"),
    },
    "patches": [],
}
args.output.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
