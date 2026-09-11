#!/usr/bin/env python3
import argparse
import json
import os
from pathlib import Path

def write_provenance(metadata_root: Path, upstream_version: str, output: Path) -> dict:
    hosts = {}
    for path in sorted(metadata_root.rglob("build-metadata.json")):
        item = json.loads(path.read_text(encoding="utf-8"))
        if item["rid"] in hosts:
            raise RuntimeError(f"duplicate metadata for {item['rid']}")
        hosts[item["rid"]] = item
    record = {
        "builder": "GitHub Actions",
        "repository": os.environ.get("GITHUB_REPOSITORY"),
        "commit": os.environ.get("GITHUB_SHA"),
        "workflow": os.environ.get("GITHUB_WORKFLOW"),
        "runId": os.environ.get("GITHUB_RUN_ID"),
        "runAttempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "event": os.environ.get("GITHUB_EVENT_NAME"),
        "hostBuilds": hosts,
        "windowsHost": {
            "origin": f"Verified official nsis-{upstream_version}.zip",
            "compilerPathInUpstream": "Bin/makensis.exe",
            "runtimeDependencyPathsInUpstream": ["Bin/zlib1.dll"],
            "patches": [],
        },
        "statement": "Inputs are hash-pinned upstream archives. Native compilers are built without patches using the recorded parameters and runner toolchains.",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return record


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metadata-root", type=Path, required=True)
    parser.add_argument("--upstream-version", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    write_provenance(args.metadata_root, args.upstream_version, args.output)


if __name__ == "__main__":
    main()
