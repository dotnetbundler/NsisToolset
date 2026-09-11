"""Load toolset configuration and resolve version tags."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "toolset.json"
DEFAULT_UPSTREAM_DIR = ROOT / "config" / "upstream"


def load_config(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def merged_config(base_path: Path, upstream_path: Path, toolset_version: str) -> dict:
    base = load_config(base_path)
    upstream = load_config(upstream_path)
    if upstream_path.stem != upstream.get("upstreamVersion"):
        raise RuntimeError(f"upstream config filename/version mismatch: {upstream_path}")
    prefix = f"{upstream['upstreamVersion']}-"
    if not toolset_version.startswith(prefix):
        raise RuntimeError(f"toolset version {toolset_version} does not use upstream {upstream['upstreamVersion']}")
    local_version = toolset_version[len(prefix) :]
    if not re.fullmatch(r"[0-9A-Za-z][0-9A-Za-z.-]*", local_version):
        raise RuntimeError(f"invalid local version label: {local_version}")
    return {**base, **upstream, "toolsetVersion": toolset_version}


def resolve_version(version: str, upstream_dir: Path = DEFAULT_UPSTREAM_DIR) -> dict[str, str]:
    if not re.fullmatch(r"v[0-9][0-9A-Za-z.-]*-[0-9A-Za-z][0-9A-Za-z.-]*", version):
        raise RuntimeError("version must have form v<upstream>-<local>, for example v3.12-r1 or v3.12-preview.2")
    candidates = []
    for path in upstream_dir.glob("*.json"):
        upstream_version = path.stem
        if version.startswith(f"v{upstream_version}-"):
            candidates.append((len(upstream_version), upstream_version, path))
    if not candidates:
        raise RuntimeError(f"no registered upstream config matches {version}")
    _, upstream_version, path = max(candidates)
    local_version = version[len(upstream_version) + 2 :]
    upstream = load_config(path)
    if upstream.get("upstreamVersion") != upstream_version:
        raise RuntimeError(f"upstream config filename/version mismatch: {path}")
    try:
        config_output = path.relative_to(ROOT).as_posix()
    except ValueError:
        config_output = path.as_posix()
    return {
        "tag": version,
        "toolsetVersion": version[1:],
        "upstreamVersion": upstream_version,
        "localVersion": local_version,
        "upstreamConfig": config_output,
        "sourceDateEpoch": str(upstream["sourceDateEpoch"]),
        "windowsArchive": upstream["upstream"]["windowsZip"]["fileName"],
        "sourceArchive": upstream["upstream"]["sourceArchive"]["fileName"],
    }
