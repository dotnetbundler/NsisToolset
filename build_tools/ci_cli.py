#!/usr/bin/env python3
"""Command-line entry point for CI-specific NSIS toolset tasks."""

from __future__ import annotations

import argparse
import subprocess
import sys
import tarfile
from pathlib import Path

from . import configuration, native_build, release_tasks, smoke_tests


class Arguments(argparse.Namespace):
    config: Path
    upstream_config: Path | None
    toolset_version: str | None
    command: str
    stage: Path
    fixture: Path
    smoke: Path
    archive: Path
    data_root: Path
    rid: str
    first: Path
    second: Path
    work: Path
    binary: Path
    metadata: Path
    hosts: Path
    artifacts: Path
    destination: Path
    installer: Path
    install_root: Path
    dist: Path


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=configuration.DEFAULT_CONFIG)
    parser.add_argument("--upstream-config", type=Path)
    parser.add_argument("--toolset-version")
    commands = parser.add_subparsers(dest="command", required=True)

    command = commands.add_parser("windows-smoke")
    command.add_argument("--stage", type=Path, required=True)
    command.add_argument("--fixture", type=Path, required=True)
    command.add_argument("--smoke", type=Path, required=True)

    command = commands.add_parser("native-build-twice")
    command.add_argument("--archive", type=Path, required=True)
    command.add_argument("--data-root", type=Path, required=True)
    command.add_argument("--rid", required=True)
    command.add_argument("--first", type=Path, required=True)
    command.add_argument("--second", type=Path, required=True)
    command.add_argument("--work", type=Path, required=True)

    command = commands.add_parser("native-smoke")
    command.add_argument("--rid", required=True)
    command.add_argument("--binary", type=Path, required=True)
    command.add_argument("--metadata", type=Path, required=True)
    command.add_argument("--stage", type=Path, required=True)
    command.add_argument("--fixture", type=Path, required=True)
    command.add_argument("--smoke", type=Path, required=True)

    command = commands.add_parser("assemble")
    command.add_argument("--stage", type=Path, required=True)
    command.add_argument("--hosts", type=Path, required=True)
    command.add_argument("--artifacts", type=Path, required=True)

    command = commands.add_parser("release-package-smoke")
    command.add_argument("--archive", type=Path, required=True)
    command.add_argument("--destination", type=Path, required=True)
    command.add_argument("--smoke", type=Path, required=True)
    command.add_argument("--fixture", type=Path, required=True)

    command = commands.add_parser("test-installer")
    command.add_argument("--installer", type=Path, required=True)
    command.add_argument("--install-root", type=Path, required=True)

    command = commands.add_parser("publish")
    command.add_argument("--dist", type=Path, required=True)
    return parser


def main() -> None:
    parser = create_parser()
    args = parser.parse_args(namespace=Arguments())
    if args.command == "test-installer":
        return release_tasks.test_installer(args.installer, args.install_root)
    if args.upstream_config is None or args.toolset_version is None:
        parser.error("--upstream-config and --toolset-version are required")
    config = configuration.merged_config(args.config, args.upstream_config, args.toolset_version)
    if args.command == "windows-smoke":
        smoke_tests.windows_smoke(config, args.stage, args.fixture, args.smoke)
    elif args.command == "native-build-twice":
        native_build.build_twice(config, args.archive, args.data_root, args.rid, args.first, args.second, args.work)
    elif args.command == "native-smoke":
        smoke_tests.native_smoke(config, args.rid, args.binary, args.metadata, args.stage, args.fixture, args.smoke)
    elif args.command == "assemble":
        release_tasks.assemble(config, args.stage, args.hosts, args.artifacts)
    elif args.command == "release-package-smoke":
        smoke_tests.release_package_smoke(config, args.archive, args.destination, args.smoke, args.fixture)
    elif args.command == "publish":
        release_tasks.publish(config, args.dist)


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.CalledProcessError, tarfile.TarError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)
