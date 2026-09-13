"""Run Linux compiler builds in pinned manylinux2014 containers."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from . import configuration
from .ci_support import run

MANYLINUX_IMAGES = {
    "linux-x64": "quay.io/pypa/manylinux2014_x86_64@sha256:493d2032114d757aaa761a9385ad8497f391503bf71acef9abeeb66682ca5d90",
    "linux-arm64": "quay.io/pypa/manylinux2014_aarch64@sha256:f4cd164263e4ec2b7da7ee40b319bb5e30f0d7a2abd7ad4730e716a512dfb529",
}


def _install_requirements() -> None:
    run([sys.executable, "-m", "pip", "install", "--require-hashes", "-r", configuration.ROOT / "requirements-build.txt"])


def prepare_container() -> None:
    """Validate and configure the pinned glibc 2.17 build environment."""
    glibc = run(["getconf", "GNU_LIBC_VERSION"], capture=True).stdout.strip()
    if glibc != "glibc 2.17":
        raise RuntimeError(f"Linux hosts must be built in the glibc 2.17 image, found {glibc!r}")

    compiler_directory = Path("/opt/rh/devtoolset-10/root/usr/bin")
    compilers = {"gcc": compiler_directory / "gcc", "g++": compiler_directory / "g++"}
    for name, compiler in compilers.items():
        if not compiler.is_file():
            raise RuntimeError(f"missing manylinux2014 compiler: {compiler}")
        alias = Path("/usr/local/bin") / name
        if not alias.exists():
            alias.symlink_to(compiler)
    os.environ.update(CC=str(compilers["gcc"]), CXX=str(compilers["g++"]))
    _install_requirements()


def _container_path(path: Path) -> Path:
    try:
        relative = path.resolve().relative_to(configuration.ROOT)
    except ValueError as error:
        raise RuntimeError(f"container build path must be inside the workspace: {path}") from error
    return Path("/workspace") / relative


def run_in_container(config_path: Path, upstream_config: Path, toolset_version: str, cache: Path, data_root: Path, rid: str, artifacts: Path) -> None:
    """Dispatch a reproducible host build to its pinned manylinux image."""
    try:
        image = MANYLINUX_IMAGES[rid]
    except KeyError as error:
        raise RuntimeError(f"unsupported Linux RID: {rid}") from error

    run(
        [
            "docker",
            "run",
            "--rm",
            "--volume",
            f"{configuration.ROOT}:/workspace",
            "--workdir",
            "/workspace",
            image,
            "/opt/python/cp312-cp312/bin/python",
            "-m",
            "build_tools.ci_cli",
            "--config",
            _container_path(config_path),
            "--upstream-config",
            _container_path(upstream_config),
            "--toolset-version",
            toolset_version,
            "native-build-twice",
            "--cache",
            _container_path(cache),
            "--data-root",
            _container_path(data_root),
            "--rid",
            rid,
            "--artifacts",
            _container_path(artifacts),
        ]
    )
