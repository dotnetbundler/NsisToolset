import io
import json
import os
import re
import shlex
import stat
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from build_tools import configuration, native_build, packaging, release_tasks, smoke_tests, staging, upstream
from build_tools.ci_cli import create_parser as create_ci_parser
from build_tools.toolset_cli import create_parser as create_toolset_parser


class ToolsetTests(unittest.TestCase):
    def make_stage(self, root: Path, toolset_version: str = "test-r1"):
        stage = root / "stage"
        for name in ("Include", "Plugins", "Stubs"):
            item = stage / "common" / name
            item.mkdir(parents=True)
            (item / "data").write_text(name)
        (stage / "common" / "Contrib").mkdir()
        (stage / "common" / "Contrib" / "data").write_text("Contrib")
        (stage / "common" / "COPYING").write_text("license")
        (stage / "common" / "nsisconf.nsh").write_text("")
        config = {
            "toolsetVersion": toolset_version,
            "upstreamVersion": "test",
            "sourceDateEpoch": 1776631488,
            "upstream": {},
            "launchers": {"windows": "makensis.cmd", "posix": "makensis"},
            "hosts": {},
        }
        staging.write_root_launchers(stage)
        hosts = (
            ("win-x86", "win-x86", "makensis.exe", False, ["win-x86", "win-x64", "win-arm64"]),
            ("linux-x64", "linux-x64", "makensis", True, ["linux-x64"]),
            ("linux-arm64", "linux-arm64", "makensis", True, ["linux-arm64"]),
            ("osx-x64", "osx-x64", "makensis", True, ["osx-x64"]),
            ("osx-arm64", "osx-arm64", "makensis", True, ["osx-arm64"]),
        )
        for rid, directory, name, executable, compatible in hosts:
            binary = stage / "hosts" / directory / name
            binary.parent.mkdir(parents=True)
            binary.write_bytes(b"binary")
            if executable:
                binary.chmod(0o755)
            config["hosts"][rid] = {
                "directory": directory,
                "binary": binary.relative_to(stage).as_posix(),
                "architecture": rid.rsplit("-", 1)[-1],
                "compatibleHostRids": compatible,
                "requiredEnvironment": {"NSISDIR": {"toolsetRelativePath": "common"}},
                "unixExecutable": executable,
                "minimumOs": "test",
            }
        (stage / "hosts" / "win-x86" / "zlib1.dll").write_bytes(b"zlib")
        return stage, config

    def make_windows_archive(self, root: Path):
        archive = root / "windows.zip"
        pe = bytearray(128)
        pe[:2] = b"MZ"
        pe[0x3C:0x40] = (64).to_bytes(4, "little")
        pe[64:68] = b"PE\0\0"
        pe[68:70] = (0x014C).to_bytes(2, "little")
        with zipfile.ZipFile(archive, "w") as bundle:
            for name in staging.COMMON_ITEMS:
                suffix = "/data" if name in {"Contrib", "Include", "Plugins", "Stubs"} else ""
                bundle.writestr(f"nsis/{name}{suffix}", name.encode())
            bundle.writestr("nsis/Bin/makensis.exe", pe)
            bundle.writestr("nsis/Bin/zlib1.dll", b"zlib")
        spec = {
            "fileName": archive.name,
            "size": archive.stat().st_size,
            "digests": {
                "upstreamPublished": {"sha1": upstream.digest(archive, "sha1"), "md5": "record-only"},
                "locallyDerived": {"sha256": upstream.sha256(archive)},
            },
        }
        config = {"upstream": {"windowsZip": spec}}
        return archive, config

    def test_version_resolution_uses_longest_registered_upstream(self):
        with tempfile.TemporaryDirectory() as temporary:
            configs = Path(temporary)
            for version in ("3.12", "3.12-preview"):
                (configs / f"{version}.json").write_text(json.dumps({"upstreamVersion": version, "sourceDateEpoch": 1, "upstream": {"windowsZip": {"fileName": "win.zip"}, "sourceArchive": {"fileName": "src.tar"}}}))
            resolved = configuration.resolve_version("v3.12-preview-r1", configs)
            self.assertEqual("3.12-preview", resolved["upstreamVersion"])
            self.assertEqual("r1", resolved["localVersion"])
            resolved = configuration.resolve_version("v3.12-preview.2", configs)
            self.assertEqual("3.12", resolved["upstreamVersion"])
            self.assertEqual("preview.2", resolved["localVersion"])

    def test_invalid_or_unregistered_version_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            configs = Path(temporary)
            for version in ("v3.12", "v3.12-../bad", "release-3.12-r1"):
                with self.subTest(version=version), self.assertRaises(RuntimeError):
                    configuration.resolve_version(version, configs)

    def test_upstream_check_requires_size_published_sha1_and_derived_sha256(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "input"
            path.write_bytes(b"fixed upstream bytes")
            spec = {"size": path.stat().st_size, "digests": {"upstreamPublished": {"sha1": upstream.digest(path, "sha1"), "md5": "record-only"}, "locallyDerived": {"sha256": upstream.sha256(path)}}}
            upstream.checked_file(path, spec)
            for key, value in (("size", 0), ("sha1", "0" * 40), ("sha256", "0" * 64)):
                changed = json.loads(json.dumps(spec))
                if key == "size":
                    changed["size"] = value
                elif key == "sha1":
                    changed["digests"]["upstreamPublished"][key] = value
                else:
                    changed["digests"]["locallyDerived"][key] = value
                with self.subTest(key=key), self.assertRaises(RuntimeError):
                    upstream.checked_file(path, changed)

    def test_unsafe_zip_members_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for index, member in enumerate(("../escape", "..\\escape", "/absolute", "C:/absolute")):
                archive = root / f"bad-{index}.zip"
                with zipfile.ZipFile(archive, "w") as bundle:
                    bundle.writestr(member, b"bad")
                with self.subTest(member=member), self.assertRaises(RuntimeError):
                    upstream.safe_extract_zip_flat(archive, root / f"out-{index}")

    def test_source_archive_extraction_requires_one_safe_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "source.tar.bz2"
            with tarfile.open(archive, "w:bz2") as bundle:
                content = b"source"
                item = tarfile.TarInfo("nsis-3.12/file.txt")
                item.size = len(content)
                bundle.addfile(item, io.BytesIO(content))
            source = native_build.safe_extract_source(archive, root / "out")
            self.assertEqual(b"source", (source / "file.txt").read_bytes())
            unsafe = root / "unsafe.tar.bz2"
            with tarfile.open(unsafe, "w:bz2") as bundle:
                item = tarfile.TarInfo("../escape")
                item.size = 1
                bundle.addfile(item, io.BytesIO(b"x"))
            with self.assertRaises(RuntimeError):
                native_build.safe_extract_source(unsafe, root / "unsafe-out")

    def test_native_build_targets_glibc_2_17_and_static_cpp_runtime(self):
        with tempfile.TemporaryDirectory(dir=configuration.ROOT) as temporary:
            root = Path(temporary)
            relative_root = root.relative_to(configuration.ROOT)
            archive = relative_root / "source.tar.bz2"
            archive.write_bytes(b"source")
            data_root = relative_root / "stage/common"
            (data_root / "Stubs").mkdir(parents=True)
            (data_root / "Stubs/uninst").write_bytes(b"stub")
            config = {
                "upstreamVersion": "3.12",
                "sourceDateEpoch": 1776631488,
                "upstream": {"sourceArchive": {}},
            }
            scons_prefixes = []
            scons_compilers = []
            scons_link_flags = []
            version_data_roots = []

            def simulate(command, **_kwargs):
                if command[:3] == [sys.executable, "-m", "SCons"]:
                    arguments = [str(item) for item in command]
                    prefix = Path(next(item.removeprefix("PREFIX=") for item in arguments if item.startswith("PREFIX=")))
                    scons_prefixes.append(prefix)
                    scons_compilers.append([item for item in arguments if item.startswith(("CC=", "CXX="))])
                    scons_link_flags.append(next(item for item in arguments if item.startswith("APPEND_LINKFLAGS=")))
                    (prefix / "makensis").write_bytes(b"compiler")
                    return mock.Mock(stdout="")
                if "-VERSION" in command:
                    version_data_roots.append(_kwargs["env"]["NSISDIR"])
                    return mock.Mock(stdout="v3.12\n")
                if Path(command[0]).name == "makensis":
                    (Path(_kwargs["cwd"]) / "legacy-codepage-smoke.exe").write_bytes(b"installer")
                    return mock.Mock(stdout="")
                if command[0] == "file":
                    return mock.Mock(stdout="ELF executable\n")
                if command[0] == "readelf":
                    if "--dynamic" in command:
                        return mock.Mock(stdout="(NEEDED) Shared library: [libc.so.6]\n")
                    if "--program-headers" in command:
                        return mock.Mock(stdout="  INTERP 0x000000\n")
                    if "--version-info" in command:
                        return mock.Mock(stdout="Name: GLIBC_2.17\n")
                    return mock.Mock(stdout="ELF report\n")
                if command[0] == "ldd":
                    return mock.Mock(stdout="libc.so.6 => /lib/libc.so.6\n", stderr="")
                self.fail(f"unexpected command: {command}")

            with (
                mock.patch.object(upstream, "checked_file"),
                mock.patch.object(native_build, "safe_extract_source", return_value=relative_root / "src/nsis"),
                mock.patch.object(native_build, "run", side_effect=simulate),
                mock.patch.object(native_build, "write_metadata"),
            ):
                native_build.build_native(config, archive, data_root, relative_root / "output", "linux-x64", relative_root / "native-work")

            self.assertEqual([(root / "native-work/install").resolve()], scons_prefixes)
            self.assertTrue(scons_prefixes[0].is_absolute())
            self.assertEqual([["CC=gcc", "CXX=g++"]], scons_compilers)
            self.assertEqual(["APPEND_LINKFLAGS=-static-libgcc -static-libstdc++"], scons_link_flags)
            self.assertEqual([str((root / "stage/common").resolve())], version_data_roots)

    def test_linux_container_build_is_dispatched_by_python(self):
        with tempfile.TemporaryDirectory(dir=configuration.ROOT) as temporary:
            root = Path(temporary)
            relative_root = root.relative_to(configuration.ROOT)
            with mock.patch.object(native_build, "run") as run:
                native_build.build_linux_in_container(
                    configuration.DEFAULT_CONFIG,
                    relative_root / "upstream.json",
                    "3.12-r1",
                    relative_root / "cache",
                    relative_root / "common",
                    "linux-x64",
                    relative_root / "artifacts",
                )

            command = run.call_args.args[0]
            self.assertEqual("docker", command[0])
            self.assertEqual(native_build.MANYLINUX_IMAGES["linux-x64"], command[7])
            self.assertIn("/opt/python/cp312-cp312/bin/python", command)
            self.assertIn("native-build-twice", command)
            self.assertNotIn("--container", command)

    def test_common_and_windows_host_are_staged_independently(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive, config = self.make_windows_archive(root)
            stage, work = root / "stage", root / "work"
            staging.stage_common(config, archive, stage, work)
            self.assertTrue((stage / "common/Include/data").is_file())
            self.assertTrue((stage / "makensis.cmd").is_file())
            self.assertFalse((stage / "hosts").exists())
            staging.stage_windows_host(config, archive, stage, work)
            self.assertTrue((stage / "hosts/win-x86/makensis.exe").is_file())
            staging.verify_windows_x86(stage / "hosts/win-x86/makensis.exe")

    def test_windows_binary_must_be_x86_pe(self):
        with tempfile.TemporaryDirectory() as temporary:
            binary = Path(temporary) / "makensis.exe"
            data = bytearray(128)
            data[:2] = b"MZ"
            data[0x3C:0x40] = (64).to_bytes(4, "little")
            data[64:68] = b"PE\0\0"
            data[68:70] = (0x8664).to_bytes(2, "little")
            binary.write_bytes(data)
            with self.assertRaises(RuntimeError):
                staging.verify_windows_x86(binary)
            data[68:70] = (0x014C).to_bytes(2, "little")
            binary.write_bytes(data)
            staging.verify_windows_x86(binary)

    def test_root_dispatchers_cover_supported_hosts(self):
        with tempfile.TemporaryDirectory() as temporary:
            stage = Path(temporary)
            staging.write_root_launchers(stage)
            windows = (stage / "makensis.cmd").read_text()
            windows_bytes = (stage / "makensis.cmd").read_bytes()
            posix = (stage / "makensis").read_text()
            self.assertIn("hosts\\win-x86\\makensis.exe", windows)
            self.assertNotIn(b"\n", windows_bytes.replace(b"\r\n", b""))
            for value in ("Linux:x86_64", "Linux:aarch64", "Darwin:x86_64", "Darwin:arm64"):
                self.assertIn(value, posix)
            self.assertIn("unsupported host", posix)

    def test_smoke_tests_invoke_only_root_launchers(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stage = root / "stage"
            staging.write_root_launchers(stage)
            fixture = root / "minimal.nsi"
            fixture.write_text("fixture")
            config = {"upstreamVersion": "3.12", "toolsetVersion": "3.12-r1"}

            def produce_installer(command, cwd=None, **_kwargs):
                Path(cwd, "smoke-installer.exe").write_bytes(b"installer")

            with mock.patch.object(smoke_tests, "run", side_effect=produce_installer) as run_mock, mock.patch.object(smoke_tests, "require_version") as version_mock:
                smoke_tests.windows_smoke(config, stage, fixture, root / "windows-smoke")
                self.assertIn(stage.resolve() / "makensis.cmd", version_mock.call_args.args[0])
                self.assertIn(stage.resolve() / "makensis.cmd", run_mock.call_args.args[0])

            metadata = root / "metadata.json"
            metadata.write_text("{}")
            binary = root / "makensis"
            binary.write_bytes(b"binary")
            with mock.patch.object(staging, "stage_host"), mock.patch.object(smoke_tests, "run", side_effect=produce_installer) as run_mock, mock.patch.object(smoke_tests, "require_version") as version_mock:
                smoke_tests.native_smoke(config, "linux-x64", binary, metadata, stage, fixture, root / "native-smoke")
                self.assertEqual(stage.resolve() / "makensis", version_mock.call_args.args[0][0])
                self.assertEqual(stage.resolve() / "makensis", run_mock.call_args.args[0][0])

            example = root / "bigtest.nsi"
            example.write_text("example")

            def produce_bigtest(command, **_kwargs):
                output = next(item.removeprefix("-XOutFile ") for item in map(str, command) if item.startswith("-XOutFile "))
                Path(output).write_bytes(b"installer")

            with mock.patch.object(smoke_tests, "run", side_effect=produce_bigtest) as run_mock, mock.patch.object(smoke_tests, "require_version"):
                smoke_tests.upstream_example_smoke(config, example, root / "upstream-example-smoke", [stage.resolve() / "makensis"])
                self.assertIn(example.resolve(), run_mock.call_args.args[0])

            release_stage, release_config = self.make_stage(root / "release", "3.12-r1")
            archive = root / "release.zip"
            packaging.deterministic_zip(release_config, release_stage, archive, release_config["sourceDateEpoch"])
            destination = root / "release package with spaces"
            with mock.patch.object(smoke_tests, "run", side_effect=produce_installer) as run_mock, mock.patch.object(smoke_tests, "require_version") as version_mock:
                smoke_tests.release_package_smoke(release_config, archive, destination, root / "release-smoke", fixture)
                self.assertEqual(destination.resolve() / "makensis", version_mock.call_args.args[0][0])
                self.assertEqual(destination.resolve() / "makensis", run_mock.call_args.args[0][0])

    def test_installer_uses_requested_artifact_directory_and_uninstalls(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installer = root / "smoke-installer.exe"
            installer.write_bytes(b"installer")
            install_root = root / "artifacts" / "installed" / "win-x86"
            commands = []

            def simulate(command, **_kwargs):
                commands.append(command)
                if command[0] == installer.resolve():
                    install_root.mkdir(parents=True)
                    (install_root / "installed.txt").write_text("installed")
                    (install_root / "uninstall.exe").write_bytes(b"uninstaller")
                else:
                    for child in install_root.iterdir():
                        child.unlink()
                    install_root.rmdir()

            with mock.patch.object(release_tasks, "run", side_effect=simulate):
                release_tasks.test_installer(installer, install_root)
            self.assertEqual(f"/D={install_root.resolve()}", commands[0][-1])
            self.assertFalse(install_root.exists())

    def test_stage_validation_rejects_non_runtime_content(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stage, config = self.make_stage(root)
            packaging.validate_stage(config, stage)
            leaked = stage / "build_tools" / "helper.py"
            leaked.parent.mkdir()
            leaked.write_text("print('leaked')")
            with self.assertRaises(RuntimeError):
                packaging.validate_stage(config, stage)

    def test_zip_is_deterministic_and_permissions_are_repairable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stage, config = self.make_stage(root)
            first, second = root / "one.zip", root / "two.zip"
            packaging.deterministic_zip(config, stage, first, config["sourceDateEpoch"])
            packaging.deterministic_zip(config, stage, second, config["sourceDateEpoch"])
            self.assertEqual(upstream.sha256(first), upstream.sha256(second))
            extracted = root / "release package with spaces"
            packaging.verify_zip(config, first, extracted)
            with zipfile.ZipFile(first) as bundle:
                self.assertEqual(0o755, bundle.getinfo("makensis").external_attr >> 16)
                self.assertEqual(packaging.RELEASE_ROOTS, {Path(name).parts[0] for name in bundle.namelist()})
                self.assertFalse(any(name.endswith((".json", ".md", ".py", ".bin")) for name in bundle.namelist()))
            if os.name != "nt":
                self.assertTrue((extracted / "makensis").stat().st_mode & stat.S_IXUSR)

    def test_local_labels_do_not_add_metadata_to_runtime_archive(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            hashes = []
            for label in ("3.12-r1", "3.12-preview.2"):
                stage, config = self.make_stage(root / label, label)
                archive = root / f"{label}.zip"
                packaging.deterministic_zip(config, stage, archive, config["sourceDateEpoch"])
                hashes.append(upstream.sha256(archive))
            self.assertEqual(hashes[0], hashes[1])

    def test_assemble_creates_complete_reproducible_release_assets(self):
        with tempfile.TemporaryDirectory() as temporary:
            artifacts = Path(temporary) / "artifacts"
            stage, config = self.make_stage(artifacts)
            hosts = artifacts / "hosts"
            for rid in ("linux-x64", "linux-arm64", "osx-x64", "osx-arm64"):
                staged_binary = stage / config["hosts"][rid]["binary"]
                binary = hosts / f"host-{rid}" / "makensis"
                binary.parent.mkdir(parents=True)
                binary.write_bytes(staged_binary.read_bytes())
                metadata = {"rid": rid, "reportedVersion": "vtest", "sha256": upstream.sha256(binary)}
                (binary.parent / "build-metadata.json").write_text(json.dumps(metadata))
                staged_binary.unlink()
                staged_binary.parent.rmdir()
            release_tasks.assemble(config, stage, hosts, artifacts)
            dist = artifacts / "dist"
            expected = {
                "nsis-toolset-test-r1.zip",
                "nsis-toolset-test-r1.zip.sha256",
            }
            self.assertEqual(expected, {path.name for path in dist.iterdir()})
            with zipfile.ZipFile(dist / "nsis-toolset-test-r1.zip") as bundle:
                self.assertEqual(packaging.RELEASE_ROOTS, {Path(name).parts[0] for name in bundle.namelist()})
                self.assertFalse(any(name.endswith((".json", ".md")) for name in bundle.namelist()))
            self.assertEqual((dist / "nsis-toolset-test-r1.zip").read_bytes(), (artifacts / "repeat/nsis-toolset-test-r1.zip").read_bytes())

    def test_unexpected_host_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            stage, config = self.make_stage(Path(temporary))
            (stage / "hosts" / "linux-x64" / "build-metadata.json").write_text("{}")
            with self.assertRaises(RuntimeError):
                packaging.validate_stage(config, stage)

    def test_cli_parsers_expose_only_current_commands(self):
        toolset_commands = set(create_toolset_parser()._subparsers._group_actions[0].choices)
        ci_commands = set(create_ci_parser()._subparsers._group_actions[0].choices)
        self.assertEqual({"resolve-version", "download", "stage-common", "stage-windows-host"}, toolset_commands)
        self.assertEqual({"host-smoke", "native-build-twice", "assemble", "release-package-smoke", "test-installer", "publish"}, ci_commands)

    def test_workflow_python_commands_match_cli_parsers(self):
        workflow = (configuration.ROOT / ".github/workflows/build.yml").read_text(encoding="utf-8")
        commands = re.findall(r"^\s*run: (python -m build_tools\.(?:toolset_cli|ci_cli) .+)$", workflow, flags=re.MULTILINE)
        self.assertGreaterEqual(len(commands), 10)
        for command in commands:
            normalized = re.sub(r"\$\{\{[^}]+\}\}", "value", command).replace("$REQUESTED_VERSION", "v3.12-r1").replace("$GITHUB_OUTPUT", "output").replace("$GITHUB_SHA", "commit")
            tokens = shlex.split(normalized)
            parser = create_toolset_parser() if tokens[2].endswith("toolset_cli") else create_ci_parser()
            with self.subTest(command=command):
                parser.parse_args(tokens[3:])

    def test_workflow_runs_all_host_and_installer_smoke_jobs(self):
        workflow = (configuration.ROOT / ".github/workflows/build.yml").read_text(encoding="utf-8")
        hosts_job = workflow.split("  hosts-smoke:", 1)[1].split("\n  installer-smoke:", 1)[0]
        matrix = re.findall(r"- \{ rid: ([^,]+), os: ([^ }]+) \}", hosts_job)
        self.assertEqual(
            [
                ("win-x86", "windows-2022"),
                ("linux-x64", "ubuntu-24.04"),
                ("linux-arm64", "ubuntu-24.04-arm"),
                ("osx-x64", "macos-15-intel"),
                ("osx-arm64", "macos-15"),
            ],
            matrix,
        )
        self.assertEqual(1, len(re.findall(r"^\s*run:", hosts_job, flags=re.MULTILINE)))
        install_job = workflow.split("  installer-smoke:", 1)[1].split("\n  assemble-and-release:", 1)[0]
        installers = re.findall(r"--installer artifacts/installers/installer-([^/]+)/", install_job)
        self.assertEqual(["win-x86", "linux-x64", "linux-arm64", "osx-x64", "osx-arm64"], installers)
        assemble_job = workflow.split("  assemble-and-release:", 1)[1]
        self.assertIn("if: github.event_name == 'push'", assemble_job)


if __name__ == "__main__":
    unittest.main()
