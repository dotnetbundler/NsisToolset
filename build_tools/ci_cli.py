#!/usr/bin/env python3
"""Command-line entry point for the build-and-release workflow."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tarfile
from pathlib import Path

from . import configuration, native_build, release, smoke_tests, upstream


class Arguments(argparse.Namespace):
    config: Path
    upstream_config: Path | None
    toolset_version: str | None
    command: str
    version: str
    upstream_dir: Path
    github_output: Path
    cache: Path
    data_root: Path
    rid: str
    artifacts: Path
    fixture: Path
    installers: Path
    install_root: Path
    stage: Path
    hosts: Path
    dist: Path


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=configuration.DEFAULT_CONFIG)
    parser.add_argument("--upstream-config", type=Path)
    parser.add_argument("--toolset-version")
    commands = parser.add_subparsers(dest="command", required=True)

    command = commands.add_parser("prepare")
    command.add_argument("--version", required=True)
    command.add_argument("--upstream-dir", type=Path, default=configuration.DEFAULT_UPSTREAM_DIR)
    command.add_argument("--github-output", type=Path, required=True)
    command.add_argument("--cache", type=Path, required=True)

    command = commands.add_parser("host-smoke")
    command.add_argument("--cache", type=Path, required=True)
    command.add_argument("--rid", required=True)
    command.add_argument("--artifacts", type=Path, required=True)
    command.add_argument("--fixture", type=Path, required=True)

    command = commands.add_parser("native-build-twice")
    command.add_argument("--cache", type=Path, required=True)
    command.add_argument("--data-root", type=Path, required=True)
    command.add_argument("--rid", required=True)
    command.add_argument("--artifacts", type=Path, required=True)

    command = commands.add_parser("installer-smoke")
    command.add_argument("--installers", type=Path, required=True)
    command.add_argument("--install-root", type=Path, required=True)

    command = commands.add_parser("assemble-and-verify")
    command.add_argument("--stage", type=Path, required=True)
    command.add_argument("--hosts", type=Path, required=True)
    command.add_argument("--artifacts", type=Path, required=True)
    command.add_argument("--fixture", type=Path, required=True)

    command = commands.add_parser("publish")
    command.add_argument("--dist", type=Path, required=True)
    return parser


def _prepare(args: Arguments) -> None:
    resolved = configuration.resolve_version(args.version, args.upstream_dir)
    print(json.dumps(resolved, indent=2, sort_keys=True))
    with args.github_output.open("a", encoding="utf-8", newline="\n") as output:
        for key, value in resolved.items():
            output.write(f"{key}={value}\n")
    upstream_config = Path(resolved["upstreamConfig"])
    config = configuration.merged_config(args.config, upstream_config, resolved["toolsetVersion"])
    upstream.download(config, args.cache)


def _load_config(args: Arguments, parser: argparse.ArgumentParser) -> dict:
    if args.upstream_config is None or args.toolset_version is None:
        parser.error("--upstream-config and --toolset-version are required")
    return configuration.merged_config(args.config, args.upstream_config, args.toolset_version)


def _host_smoke(config: dict, args: Arguments) -> None:
    smoke_tests.host_smoke(config, args.config, args.upstream_config, args.toolset_version, args.cache, args.rid, args.artifacts, args.fixture)


def _native_build_twice(config: dict, args: Arguments) -> None:
    native_build.build_reproducibly_from_cache(config, args.cache, args.data_root, args.rid, args.artifacts)


def _installer_smoke(config: dict, args: Arguments) -> None:
    smoke_tests.test_all_installers(config, args.installers, args.install_root)


def _assemble_and_verify(config: dict, args: Arguments) -> None:
    archive = release.assemble(config, args.stage, args.hosts, args.artifacts)
    smoke_tests.release_package_smoke(config, archive, args.artifacts / "release package", args.artifacts / "release package smoke", args.fixture)


def _publish(config: dict, args: Arguments) -> None:
    release.publish(config, args.dist)


COMMANDS = {
    "host-smoke": _host_smoke,
    "native-build-twice": _native_build_twice,
    "installer-smoke": _installer_smoke,
    "assemble-and-verify": _assemble_and_verify,
    "publish": _publish,
}


def main() -> None:
    parser = create_parser()
    args = parser.parse_args(namespace=Arguments())
    if args.command == "prepare":
        return _prepare(args)
    config = _load_config(args, parser)
    COMMANDS[args.command](config, args)


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.CalledProcessError, tarfile.TarError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)
