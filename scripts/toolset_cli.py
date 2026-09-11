#!/usr/bin/env python3
"""Command-line interface for reusable NSIS toolset operations."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import toolset_operations as toolset


class Arguments(argparse.Namespace):
    config: Path
    upstream_config: Path | None
    toolset_version: str | None
    command: str
    version: str
    upstream_dir: Path
    github_output: Path | None
    cache: Path
    archive: Path
    stage: Path
    work: Path
    rid: str
    binary: Path
    metadata: Path | None
    source_commit: str
    output: Path
    repair_modes: bool
    dist: Path
    destination: Path


def resolve_version_command(version: str, upstream_dir: Path, github_output: Path | None) -> None:
    resolved = toolset.resolve_version(version, upstream_dir)
    print(json.dumps(resolved, indent=2, sort_keys=True))
    if github_output is not None:
        with github_output.open("a", encoding="utf-8", newline="\n") as output:
            for key, value in resolved.items():
                output.write(f"{key}={value}\n")


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=toolset.DEFAULT_CONFIG)
    parser.add_argument("--upstream-config", type=Path)
    parser.add_argument("--toolset-version")
    commands = parser.add_subparsers(dest="command", required=True)

    command = commands.add_parser("resolve-version")
    command.add_argument("--version", required=True)
    command.add_argument("--upstream-dir", type=Path, default=toolset.DEFAULT_UPSTREAM_DIR)
    command.add_argument("--github-output", type=Path)

    command = commands.add_parser("download")
    command.add_argument("--cache", type=Path, required=True)

    command = commands.add_parser("stage-windows")
    command.add_argument("--archive", type=Path, required=True)
    command.add_argument("--stage", type=Path, required=True)
    command.add_argument("--work", type=Path, required=True)

    command = commands.add_parser("stage-host")
    command.add_argument("--stage", type=Path, required=True)
    command.add_argument("--rid", required=True)
    command.add_argument("--binary", type=Path, required=True)
    command.add_argument("--metadata", type=Path)

    command = commands.add_parser("build-record")
    command.add_argument("--stage", type=Path, required=True)
    command.add_argument("--source-commit", required=True)

    command = commands.add_parser("source-record")
    command.add_argument("--output", type=Path, required=True)

    command = commands.add_parser("manifest")
    command.add_argument("--stage", type=Path, required=True)

    command = commands.add_parser("verify")
    command.add_argument("--stage", type=Path, required=True)
    command.add_argument("--repair-modes", action="store_true")

    command = commands.add_parser("package")
    command.add_argument("--stage", type=Path, required=True)
    command.add_argument("--dist", type=Path, required=True)

    command = commands.add_parser("verify-zip")
    command.add_argument("--archive", type=Path, required=True)
    command.add_argument("--destination", type=Path, required=True)
    return parser


def main() -> None:
    parser = create_parser()
    args = parser.parse_args(namespace=Arguments())
    if args.command == "resolve-version":
        return resolve_version_command(args.version, args.upstream_dir, args.github_output)
    if args.upstream_config is None or args.toolset_version is None:
        parser.error("--upstream-config and --toolset-version are required")
    config = toolset.merged_config(args.config, args.upstream_config, args.toolset_version)
    if args.command == "download":
        toolset.download(config, args.cache)
    elif args.command == "stage-windows":
        toolset.stage_windows(config, args.archive, args.stage, args.work)
    elif args.command == "stage-host":
        toolset.stage_host(config, args.stage, args.rid, args.binary, args.metadata)
    elif args.command == "build-record":
        toolset.write_build_record(config, args.stage, args.source_commit)
    elif args.command == "source-record":
        toolset.write_source_record(config, args.output)
    elif args.command == "manifest":
        toolset.generate_manifest(config, args.stage)
    elif args.command == "verify":
        toolset.verify_manifest(args.stage, args.repair_modes)
    elif args.command == "package":
        toolset.package(config, args.stage, args.dist)
    elif args.command == "verify-zip":
        toolset.verify_zip(args.archive, args.destination)


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)
