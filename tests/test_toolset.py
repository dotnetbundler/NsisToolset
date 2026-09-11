import io
import json
import os
import stat
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

from build_tools import native_build
from build_tools import toolset_operations as toolset


class ToolsetTests(unittest.TestCase):
    def make_stage(self, root: Path, toolset_version: str = "test-r1"):
        stage = root / "stage"
        for name in ("Include", "Plugins", "Stubs"):
            item = stage / "common" / name
            item.mkdir(parents=True)
            (item / "data").write_text(name)
        (stage / "common" / "Contrib").mkdir()
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
        (stage / "makensis.cmd").write_text("launcher")
        (stage / "makensis").write_text("#!/bin/sh\n")
        (stage / "makensis").chmod(0o755)
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
        return stage, config

    def test_zip_is_deterministic_and_permissions_are_repairable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stage, config = self.make_stage(root)
            toolset.generate_manifest(config, stage)
            first, second = root / "one.zip", root / "two.zip"
            toolset.deterministic_zip(stage, first, config["sourceDateEpoch"])
            toolset.deterministic_zip(stage, second, config["sourceDateEpoch"])
            self.assertEqual(toolset.sha256(first), toolset.sha256(second))
            extracted = root / "extracted"
            toolset.safe_extract_zip_flat(first, extracted)
            manifest = toolset.verify_manifest(extracted, repair_modes=True)
            self.assertEqual(5, len(manifest["hosts"]))
            self.assertEqual("x86", manifest["hosts"][0]["architecture"])
            self.assertIn("win-arm64", manifest["hosts"][0]["compatibleHostRids"])
            self.assertNotIn("convenienceLauncher", manifest["hosts"][0])
            executable = next(item for item in manifest["files"] if item["path"] == "makensis")
            self.assertTrue(executable["requiresExecutable"])
            with zipfile.ZipFile(first) as bundle:
                self.assertEqual(0o755, bundle.getinfo("makensis").external_attr >> 16)
                self.assertFalse(
                    any(name.endswith(".py") or name.endswith(".bin") for name in bundle.namelist())
                )
            if os.name != "nt":
                self.assertTrue((extracted / "makensis").stat().st_mode & stat.S_IXUSR)

    def test_local_labels_produce_distinct_manifests_and_archives(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            hashes = []
            for label in ("3.12-r1", "3.12-preview.2"):
                stage, config = self.make_stage(root / label, label)
                toolset.generate_manifest(config, stage)
                archive = root / (label + ".zip")
                toolset.deterministic_zip(stage, archive, config["sourceDateEpoch"])
                hashes.append(toolset.sha256(archive))
            self.assertNotEqual(hashes[0], hashes[1])

    def test_version_resolution_uses_longest_registered_upstream(self):
        with tempfile.TemporaryDirectory() as temporary:
            configs = Path(temporary)
            for version in ("3.12", "3.12-preview"):
                (configs / (version + ".json")).write_text(
                    json.dumps(
                        {
                            "upstreamVersion": version,
                            "sourceDateEpoch": 1,
                            "upstream": {
                                "windowsZip": {"fileName": "win.zip"},
                                "sourceArchive": {"fileName": "src.tar"},
                            },
                        }
                    )
                )
            resolved = toolset.resolve_version("v3.12-preview-r1", configs)
            self.assertEqual("3.12-preview", resolved["upstreamVersion"])
            self.assertEqual("r1", resolved["localVersion"])
            resolved = toolset.resolve_version("v3.12-preview.2", configs)
            self.assertEqual("3.12", resolved["upstreamVersion"])
            self.assertEqual("preview.2", resolved["localVersion"])

    def test_invalid_or_unregistered_version_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            configs = Path(temporary)
            with self.assertRaises(RuntimeError):
                toolset.resolve_version("v3.12", configs)
            with self.assertRaises(RuntimeError):
                toolset.resolve_version("v3.12-../bad", configs)
            with self.assertRaises(RuntimeError):
                toolset.resolve_version("release-3.12-r1", configs)

    def test_tampering_is_detected(self):
        with tempfile.TemporaryDirectory() as temporary:
            stage = Path(temporary)
            payload = stage / "payload"
            payload.write_text("good")
            manifest = {
                "toolsetVersion": "test",
                "launchers": {"windows": "makensis.cmd", "posix": "makensis"},
                "hosts": [],
                "files": [toolset.file_record(stage, payload)],
            }
            (stage / "toolset-manifest.json").write_text(json.dumps(manifest))
            payload.write_text("bad")
            with self.assertRaises(RuntimeError):
                toolset.verify_manifest(stage)

    def test_unsafe_zip_member_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "bad.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("../escape", b"bad")
            with self.assertRaises(RuntimeError):
                toolset.safe_extract_zip_flat(archive, Path(temporary) / "out")

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

    def test_upstream_check_requires_published_sha1_and_derived_sha256(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "input"
            path.write_bytes(b"fixed upstream bytes")
            spec = {
                "size": path.stat().st_size,
                "digests": {
                    "upstreamPublished": {
                        "sha1": toolset.digest(path, "sha1"),
                        "md5": "record-only",
                    },
                    "locallyDerived": {"sha256": toolset.sha256(path)},
                },
            }
            toolset.checked_file(path, spec)
            spec["digests"]["upstreamPublished"]["sha1"] = "0" * 40
            with self.assertRaises(RuntimeError):
                toolset.checked_file(path, spec)

    def test_python_build_script_cannot_leak_into_toolset(self):
        with tempfile.TemporaryDirectory() as temporary:
            stage, config = self.make_stage(Path(temporary))
            leaked = stage / "scripts" / "toolset.py"
            leaked.parent.mkdir()
            leaked.write_text("print('leaked')")
            with self.assertRaises(RuntimeError):
                toolset.generate_manifest(config, stage)

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
                toolset.verify_windows_x86(binary)
            data[68:70] = (0x014C).to_bytes(2, "little")
            binary.write_bytes(data)
            toolset.verify_windows_x86(binary)

    def test_root_dispatchers_cover_supported_hosts(self):
        with tempfile.TemporaryDirectory() as temporary:
            stage = Path(temporary)
            toolset.write_root_launchers(stage)
            windows = (stage / "makensis.cmd").read_text()
            posix = (stage / "makensis").read_text()
            self.assertIn("hosts\\win-x86\\makensis.exe", windows)
            for value in ("Linux:x86_64", "Linux:aarch64", "Darwin:x86_64", "Darwin:arm64"):
                self.assertIn(value, posix)
            self.assertIn("unsupported host", posix)


if __name__ == "__main__":
    unittest.main()
