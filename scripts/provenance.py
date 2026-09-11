#!/usr/bin/env python3
import argparse
import json
import os
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--metadata-root", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()

hosts = {}
for path in sorted(args.metadata_root.rglob("build-metadata.json")):
    item = json.loads(path.read_text(encoding="utf-8"))
    if item["rid"] in hosts:
        raise SystemExit(f"duplicate metadata for {item['rid']}")
    hosts[item["rid"]] = item

provenance = {
    "builder": "GitHub Actions",
    "repository": os.environ.get("GITHUB_REPOSITORY"),
    "commit": os.environ.get("GITHUB_SHA"),
    "workflow": os.environ.get("GITHUB_WORKFLOW"),
    "runId": os.environ.get("GITHUB_RUN_ID"),
    "runAttempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
    "event": os.environ.get("GITHUB_EVENT_NAME"),
    "hostBuilds": hosts,
    "windowsHost": {
        "origin": "Verified official nsis-3.12.zip",
        "compilerPathInUpstream": "Bin/makensis.exe",
        "runtimeDependencyPathsInUpstream": ["Bin/zlib1.dll"],
        "patches": [],
    },
    "statement": "Inputs are hash-pinned upstream archives. Native compilers are built without patches using the recorded parameters and runner toolchains.",
}
args.output.write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
