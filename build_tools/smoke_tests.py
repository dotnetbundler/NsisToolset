"""End-to-end checks that exercise toolset root launchers."""

from __future__ import annotations

import shutil
from pathlib import Path

from . import native_build, packaging, staging
from .ci_support import recreate, require_version, run


def _compile_with_launcher(config: dict, stage: Path, fixture: Path, smoke: Path, launcher: list[str | Path]) -> None:
    recreate(smoke)
    shutil.copy2(fixture, smoke / fixture.name)
    require_version([*launcher, "-VERSION"], config["upstreamVersion"], cwd=smoke)
    run([*launcher, fixture.name], cwd=smoke)
    if not (smoke / "smoke-installer.exe").is_file():
        raise RuntimeError("root launcher smoke test did not produce an installer")


def windows_smoke(config: dict, stage: Path, fixture: Path, smoke: Path) -> None:
    launcher = ["cmd.exe", "/d", "/c", stage.resolve() / "makensis.cmd"]
    _compile_with_launcher(config, stage, fixture, smoke, launcher)


def native_smoke(config: dict, rid: str, binary: Path, metadata: Path, stage: Path, fixture: Path, smoke: Path) -> None:
    staging.stage_host(config, stage, rid, binary, metadata)
    launcher = stage.resolve() / "makensis"
    launcher.chmod(0o755)
    _compile_with_launcher(config, stage, fixture, smoke, [launcher])


def upstream_example_smoke(config: dict, example: Path, smoke: Path, launcher: list[str | Path]) -> None:
    """Compile the official bigtest example, matching Homebrew's functional test."""
    recreate(smoke)
    output = (smoke / "bigtest-installer.exe").resolve()
    require_version([*launcher, "-VERSION"], config["upstreamVersion"], cwd=smoke)
    run([*launcher, example.resolve(), f"-XOutFile {output}"], cwd=smoke)
    if not output.is_file():
        raise RuntimeError("official bigtest example did not produce an installer")


def host_smoke(config: dict, config_path: Path, upstream_config: Path, toolset_version: str, cache: Path, rid: str, artifacts: Path, fixture: Path) -> None:
    archive = cache / config["upstream"]["windowsZip"]["fileName"]
    stage = artifacts / "stage"
    upstream_root = staging.stage_common(config, archive, stage, artifacts / "work")
    if rid == "win-x86":
        staging.stage_windows_host(config, archive, stage, artifacts / "work")
        launcher = ["cmd.exe", "/d", "/c", stage.resolve() / "makensis.cmd"]
        windows_smoke(config, stage, fixture, artifacts / "smoke")
    else:
        native_build.build_host(config, config_path, upstream_config, toolset_version, cache, stage / "common", rid, artifacts)
        launcher = [stage.resolve() / "makensis"]
        native_smoke(config, rid, artifacts / "native-1/makensis", artifacts / "native-1/build-metadata.json", stage, fixture, artifacts / "smoke")
    upstream_example_smoke(config, upstream_root / "Examples/bigtest.nsi", artifacts / "upstream-example-smoke", launcher)


def release_package_smoke(config: dict, archive: Path, destination: Path, smoke: Path, fixture: Path) -> None:
    packaging.verify_zip(config, archive, destination)
    _compile_with_launcher(config, destination, fixture, smoke, [destination.resolve() / "makensis"])
