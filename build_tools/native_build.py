"""Build and audit native NSIS compiler binaries."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

from . import configuration, upstream
from .ci_support import recreate, run


MANYLINUX_IMAGES = {
    "linux-x64": "quay.io/pypa/manylinux2014_x86_64@sha256:493d2032114d757aaa761a9385ad8497f391503bf71acef9abeeb66682ca5d90",
    "linux-arm64": "quay.io/pypa/manylinux2014_aarch64@sha256:f4cd164263e4ec2b7da7ee40b319bb5e30f0d7a2abd7ad4730e716a512dfb529",
}


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace").strip()


def write_metadata(*, rid: str, binary: Path, version_file: Path, file_report: Path, dependencies: Path, upstream_version: str, source_date_epoch: str, output: Path, environment: dict[str, str]) -> dict:
    data = binary.read_bytes()
    metadata = {
        "rid": rid,
        "sha256": hashlib.sha256(data).hexdigest(),
        "size": len(data),
        "reportedVersion": read_text(version_file),
        "binaryFormat": read_text(file_report),
        "dynamicDependencies": read_text(dependencies).splitlines(),
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
            "linuxLibc": "glibc" if rid.startswith("linux-") else None,
            "linuxGlibcBaseline": "2.17" if rid.startswith("linux-") else None,
            "macosDeploymentTarget": environment.get("MACOSX_DEPLOYMENT_TARGET"),
        },
        "patches": [],
    }
    output.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return metadata


def safe_extract_source(archive: Path, destination: Path) -> Path:
    recreate(destination)
    with tarfile.open(archive, "r:*") as bundle:
        roots: set[str] = set()
        for member in bundle.getmembers():
            relative = upstream.safe_archive_path(member.name)
            roots.add(relative.parts[0])
        if len(roots) != 1:
            raise RuntimeError(f"expected one source archive root, found {len(roots)}")
        bundle.extractall(destination, filter="data")
    source = destination / next(iter(roots))
    if not source.is_dir():
        raise RuntimeError("source archive root is not a directory")
    return source


def verify_legacy_codepage(binary: Path, work: Path, environment: dict[str, str]) -> None:
    """Require legacy code-page support, not only a runnable binary."""
    script = work / "legacy-codepage-smoke.nsi"
    script.write_text(
        """!pragma warning error all
Unicode true
Name "Legacy code-page smoke"
OutFile "legacy-codepage-smoke.exe"
RequestExecutionLevel user
LoadLanguageFile "${NSISDIR}\\Contrib\\Language files\\English.nlf"
LoadLanguageFile "${NSISDIR}\\Contrib\\Language files\\SimpChinese.nlf"
Section
SectionEnd
""",
        encoding="utf-8",
        newline="\n",
    )
    run([binary, script.resolve()], cwd=work, env=environment)
    if not (work / "legacy-codepage-smoke.exe").is_file():
        raise RuntimeError("Linux makensis did not compile the legacy code-page smoke script")


def version_tuple(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split("."))


def prepare_linux_build_environment() -> None:
    """Prepare the pinned manylinux2014 image for the native build."""
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
    os.environ["CC"] = str(compilers["gcc"])
    os.environ["CXX"] = str(compilers["g++"])
    install_build_requirements()


def install_build_requirements() -> None:
    run([sys.executable, "-m", "pip", "install", "--require-hashes", "-r", configuration.ROOT / "requirements-build.txt"])


def build_linux_in_container(config_path: Path, upstream_config: Path, toolset_version: str, cache: Path, data_root: Path, rid: str, artifacts: Path) -> None:
    """Run the complete Linux build in the pinned glibc 2.17 container."""
    try:
        image = MANYLINUX_IMAGES[rid]
    except KeyError as error:
        raise RuntimeError(f"unsupported container RID: {rid}") from error

    def workspace_path(path: Path) -> Path:
        try:
            relative = path.resolve().relative_to(configuration.ROOT)
        except ValueError as error:
            raise RuntimeError(f"container build path must be inside the workspace: {path}") from error
        return Path("/workspace") / relative

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
            workspace_path(config_path),
            "--upstream-config",
            workspace_path(upstream_config),
            "--toolset-version",
            toolset_version,
            "native-build-twice",
            "--cache",
            workspace_path(cache),
            "--data-root",
            workspace_path(data_root),
            "--rid",
            rid,
            "--artifacts",
            workspace_path(artifacts),
        ]
    )


def build_host(config: dict, config_path: Path, upstream_config: Path, toolset_version: str, cache: Path, data_root: Path, rid: str, artifacts: Path) -> None:
    if rid not in {"linux-x64", "linux-arm64", "osx-x64", "osx-arm64"}:
        raise RuntimeError(f"unsupported native host RID: {rid}")
    if rid.startswith("linux-"):
        return build_linux_in_container(config_path, upstream_config, toolset_version, cache, data_root, rid, artifacts)
    install_build_requirements()
    build_twice_from_cache(config, cache, data_root, rid, artifacts)


def build_twice_from_cache(config: dict, cache: Path, data_root: Path, rid: str, artifacts: Path) -> None:
    if rid.startswith("linux-"):
        prepare_linux_build_environment()
    source = cache / config["upstream"]["sourceArchive"]["fileName"]
    build_twice(config, source, data_root, rid, artifacts / "native-1", artifacts / "native-2", artifacts / "native-work")


def build_native(config: dict, archive: Path, data_root: Path, output: Path, rid: str, work: Path) -> None:
    if rid not in {"linux-x64", "linux-arm64", "osx-x64", "osx-arm64"}:
        raise RuntimeError(f"unsupported RID: {rid}")
    upstream.checked_file(archive, config["upstream"]["sourceArchive"])
    recreate(work)
    recreate(output)
    source = safe_extract_source(archive, work / "src")
    data_root = data_root.resolve()
    if not (data_root / "Stubs/uninst").is_file():
        raise RuntimeError(f"NSIS data root does not contain Stubs/uninst: {data_root}")
    install = (work / "install").resolve()
    install.mkdir()

    version = config["upstreamVersion"]
    components = version.split(".")
    if not 2 <= len(components) <= 4 or not all(item.isdigit() for item in components):
        raise RuntimeError(f"unsupported NSIS numeric version: {version}")
    components += ["0"] * (4 - len(components))
    environment = os.environ.copy()
    # makensis initializes its default compressor and loads Stubs/uninst before
    # it handles -VERSION, so even the version probe requires a complete data
    # root when NSIS_CONFIG_CONST_DATA_PATH is disabled.
    environment["NSISDIR"] = str(data_root)
    environment["SOURCE_DATE_EPOCH"] = str(config["sourceDateEpoch"])
    command = [
        "scons",
        "-C",
        source,
        "-j2",
        f"VERSION={version}",
        f"VER_MAJOR={components[0]}",
        f"VER_MINOR={components[1]}",
        f"VER_REVISION={components[2]}",
        f"VER_BUILD={components[3]}",
        f"SOURCE_DATE_EPOCH={config['sourceDateEpoch']}",
        "NSIS_CONFIG_CONST_DATA_PATH=no",
        f"PREFIX={install}",
        "SKIPSTUBS=all",
        "SKIPPLUGINS=all",
        "SKIPUTILS=all",
        "SKIPMISC=all",
        "SKIPDOC=all",
    ]
    if rid.startswith("linux-"):
        command.extend(
            [
                f"CC={environment.get('CC', 'gcc')}",
                f"CXX={environment.get('CXX', 'g++')}",
                "APPEND_LINKFLAGS=-static-libgcc -static-libstdc++",
            ]
        )
    elif rid == "osx-x64":
        environment["MACOSX_DEPLOYMENT_TARGET"] = "10.13"
        command.extend(["APPEND_CCFLAGS=-mmacosx-version-min=10.13", "APPEND_LINKFLAGS=-mmacosx-version-min=10.13"])
    else:
        environment["MACOSX_DEPLOYMENT_TARGET"] = "11.0"
        command.extend(["APPEND_CCFLAGS=-mmacosx-version-min=11.0", "APPEND_LINKFLAGS=-mmacosx-version-min=11.0"])
    command.append("install-compiler")
    run(command, env=environment)

    binary = (output / "makensis").resolve()
    shutil.copy2(install / "makensis", binary)
    binary.chmod(0o755)
    version_result = run([binary, "-VERSION"], env=environment, capture=True)
    (output / "version.txt").write_text(version_result.stdout, encoding="utf-8", newline="\n")
    if version_result.stdout.strip() != f"v{version}":
        raise RuntimeError(f"built compiler reported {version_result.stdout.strip()!r}")

    file_result = run(["file", binary], capture=True)
    (output / "file.txt").write_text(file_result.stdout, encoding="utf-8", newline="\n")
    if rid.startswith("linux-"):
        notes = run(["readelf", "--notes", binary], capture=True).stdout
        (output / "elf-notes.txt").write_text(notes, encoding="utf-8", newline="\n")
        dynamic = run(["readelf", "--dynamic", binary], capture=True).stdout
        needed = set(re.findall(r"\(NEEDED\).*Shared library: \[([^]]+)]", dynamic))
        loader = "ld-linux-x86-64.so.2" if rid == "linux-x64" else "ld-linux-aarch64.so.1"
        allowed = {loader, "libc.so.6", "libdl.so.2", "libm.so.6", "libpthread.so.0", "librt.so.1", "libz.so.1"}
        if not needed or needed - allowed:
            raise RuntimeError(f"unexpected Linux dynamic dependencies: {sorted(needed)}")
        program_headers = run(["readelf", "--program-headers", binary], capture=True).stdout
        if not re.search(r"^\s*INTERP\s", program_headers, flags=re.MULTILINE):
            raise RuntimeError("Linux makensis must have a glibc dynamic interpreter")
        versions = run(["readelf", "--version-info", binary], capture=True).stdout
        glibc_versions = {match for match in re.findall(r"\bGLIBC_(\d+(?:\.\d+)+)\b", versions)}
        if not glibc_versions or max(map(version_tuple, glibc_versions)) > (2, 17):
            raise RuntimeError(f"Linux makensis exceeds the GLIBC_2.17 baseline: {sorted(glibc_versions, key=version_tuple)}")
        if re.search(r"\b(?:GLIBCXX|CXXABI)_", versions):
            raise RuntimeError("Linux makensis must statically link the C++ runtime")
        dependency_result = run(["ldd", binary], capture=True, check=False)
        dependencies = dependency_result.stdout + dependency_result.stderr
        if "not found" in dependencies:
            raise RuntimeError(f"Linux makensis has unresolved dependencies:\n{dependencies}")
        verify_legacy_codepage(binary, work, environment)
    else:
        dependencies = run(["otool", "-L", binary], capture=True).stdout
        for line in dependencies.splitlines()[1:]:
            dependency = line.strip()
            if dependency and not dependency.startswith(("/usr/lib/", "/System/Library/")):
                raise RuntimeError(f"macOS makensis has a non-system dependency: {dependency}")
    (output / "dependencies.txt").write_text(dependencies, encoding="utf-8", newline="\n")
    write_metadata(
        rid=rid,
        binary=binary,
        version_file=output / "version.txt",
        file_report=output / "file.txt",
        dependencies=output / "dependencies.txt",
        upstream_version=version,
        source_date_epoch=str(config["sourceDateEpoch"]),
        output=output / "build-metadata.json",
        environment=environment,
    )


def build_twice(config: dict, archive: Path, data_root: Path, rid: str, first: Path, second: Path, work: Path) -> None:
    build_native(config, archive, data_root, first, rid, work / f"{rid}-1")
    build_native(config, archive, data_root, second, rid, work / f"{rid}-2")
    if (first / "makensis").read_bytes() != (second / "makensis").read_bytes():
        raise RuntimeError(f"repeated {rid} builds produced different compiler bytes")
    print(f"repeated {rid} builds are byte-identical")
