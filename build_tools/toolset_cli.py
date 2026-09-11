#!/usr/bin/env python3
"""Command-line interface for reusable NSIS toolset operations."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from . import configuration, staging, upstream


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


def resolve_version_command(version: str, upstream_dir: Path, github_output: Path | None) -> None:
    resolved = configuration.resolve_version(version, upstream_dir)
    print(json.dumps(resolved, indent=2, sort_keys=True))
    if github_output is not None:
        with github_output.open("a", encoding="utf-8", newline="\n") as output:
            for key, value in resolved.items():
                output.write(f"{key}={value}\n")


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=configuration.DEFAULT_CONFIG)
    parser.add_argument("--upstream-config", type=Path)
    parser.add_argument("--toolset-version")
    commands = parser.add_subparsers(dest="command", required=True)

    command = commands.add_parser("resolve-version")
    command.add_argument("--version", required=True)
    command.add_argument("--upstream-dir", type=Path, default=configuration.DEFAULT_UPSTREAM_DIR)
    command.add_argument("--github-output", type=Path)

    command = commands.add_parser("download")
    command.add_argument("--cache", type=Path, required=True)

    command = commands.add_parser("stage-common")
    command.add_argument("--archive", type=Path, required=True)
    command.add_argument("--stage", type=Path, required=True)
    command.add_argument("--work", type=Path, required=True)

    command = commands.add_parser("stage-windows-host")
    command.add_argument("--archive", type=Path, required=True)
    command.add_argument("--stage", type=Path, required=True)
    command.add_argument("--work", type=Path, required=True)
    return parser


def main() -> None:
    parser = create_parser()
    args = parser.parse_args(namespace=Arguments())
    if args.command == "resolve-version":
        return resolve_version_command(args.version, args.upstream_dir, args.github_output)
    if args.upstream_config is None or args.toolset_version is None:
        parser.error("--upstream-config and --toolset-version are required")
    config = configuration.merged_config(args.config, args.upstream_config, args.toolset_version)
    if args.command == "download":
        upstream.download(config, args.cache)
    elif args.command == "stage-common":
        staging.stage_common(config, args.archive, args.stage, args.work)
    elif args.command == "stage-windows-host":
        staging.stage_windows_host(config, args.archive, args.stage, args.work)


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)
