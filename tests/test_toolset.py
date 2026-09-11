import json
import os
import stat
import tempfile
import unittest
import zipfile
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import toolset


class ToolsetTests(unittest.TestCase):
    def test_zip_is_deterministic_and_permissions_are_repairable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stage = root / "stage"
            for name in ("Include", "Plugins", "Stubs"):
                (stage / "common" / name).mkdir(parents=True)
                (stage / "common" / name / "data").write_text(name)
            (stage / "common" / "Contrib").mkdir()
            (stage / "common" / "COPYING").write_text("license")
            (stage / "common" / "nsisconf.nsh").write_text("")
            config = {
                "toolsetVersion": "test-r1", "upstreamVersion": "test", "sourceDateEpoch": 1776631488,
                "upstream": {}, "hosts": {}
            }
            hosts = (
                ("win-x64", "win", True),
                ("linux-x64", "linux-x64", False),
                ("linux-arm64", "linux-arm64", False),
                ("osx-x64", "osx-x64", False),
                ("osx-arm64", "osx-arm64", False),
            )
            for rid, directory, win in hosts:
                host = stage / "hosts" / directory
                host.mkdir(parents=True)
                binary = host / ("makensis.exe" if win else "makensis.bin")
                binary.write_bytes(b"binary")
                entry = host / ("makensis.cmd" if win else "makensis")
                entry.write_text("launcher")
                if not win:
                    entry.chmod(0o755); binary.chmod(0o755)
                config["hosts"][rid] = {
                    "directory": directory,
                    "binary": binary.relative_to(stage).as_posix(),
                    "requiredEnvironment": {"NSISDIR": {"toolsetRelativePath": "common"}},
                    "convenienceLauncher": entry.relative_to(stage).as_posix(),
                    "unixExecutable": not win,
                    "minimumOs": "test",
                }
                if not win:
                    metadata = stage / "build" / "hosts" / f"{rid}.json"
                    metadata.parent.mkdir(parents=True, exist_ok=True)
                    metadata.write_text(json.dumps({
                        "rid": rid,
                        "reportedVersion": "vtest",
                        "sha256": toolset.sha256(binary),
                    }))
            toolset.generate_manifest(config, stage)
            first, second = root / "one.zip", root / "two.zip"
            toolset.deterministic_zip(stage, first, config["sourceDateEpoch"])
            toolset.deterministic_zip(stage, second, config["sourceDateEpoch"])
            self.assertEqual(toolset.sha256(first), toolset.sha256(second))
            extracted = root / "extracted"
            toolset.safe_extract_zip_flat(first, extracted)
            manifest = toolset.verify_manifest(extracted, repair_modes=True)
            self.assertEqual(5, len(manifest["hosts"]))
            self.assertTrue(all(host["requiredEnvironment"]["NSISDIR"]["toolsetRelativePath"] == "common" for host in manifest["hosts"]))
            launcher = next(item for item in manifest["files"] if item["path"] == "hosts/linux-x64/makensis")
            self.assertTrue(launcher["requiresExecutable"])
            self.assertEqual("0755", launcher["unixMode"])
            with zipfile.ZipFile(first) as bundle:
                archived_mode = bundle.getinfo("hosts/linux-x64/makensis").external_attr >> 16
                self.assertFalse(any(name.endswith(".py") for name in bundle.namelist()))
            self.assertEqual(0o755, archived_mode)
            if os.name != "nt":
                self.assertTrue((extracted / "hosts/linux-x64/makensis").stat().st_mode & stat.S_IXUSR)

    def test_tampering_is_detected(self):
        with tempfile.TemporaryDirectory() as temporary:
            stage = Path(temporary)
            payload = stage / "payload"
            payload.write_text("good")
            manifest = {"toolsetVersion": "test", "hosts": [], "files": [toolset.file_record(stage, payload)]}
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

    def test_upstream_check_requires_published_sha1_and_derived_sha256(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "input"
            path.write_bytes(b"fixed upstream bytes")
            spec = {
                "size": path.stat().st_size,
                "digests": {
                    "upstreamPublished": {"sha1": toolset.digest(path, "sha1"), "md5": "record-only"},
                    "locallyDerived": {"sha256": toolset.sha256(path)},
                },
            }
            toolset.checked_file(path, spec)
            spec["digests"]["upstreamPublished"]["sha1"] = "0" * 40
            with self.assertRaises(RuntimeError):
                toolset.checked_file(path, spec)

    def test_python_build_script_cannot_leak_into_toolset(self):
        with tempfile.TemporaryDirectory() as temporary:
            stage = Path(temporary)
            for name in ("Include", "Plugins", "Stubs"):
                (stage / "common" / name).mkdir(parents=True)
                (stage / "common" / name / "data").write_text(name)
            leaked = stage / "scripts" / "toolset.py"
            leaked.parent.mkdir()
            leaked.write_text("print('leaked')")
            config = {"toolsetVersion": "test", "upstreamVersion": "test", "sourceDateEpoch": 0, "upstream": {}, "hosts": {}}
            with self.assertRaises(RuntimeError):
                toolset.generate_manifest(config, stage)


if __name__ == "__main__":
    unittest.main()
