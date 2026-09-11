"""Download, verify, and safely extract upstream archives."""

from __future__ import annotations

import hashlib
import shutil
import time
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath


def safe_archive_path(name: str) -> PurePosixPath:
    relative = PurePosixPath(name.replace("\\", "/"))
    if relative.is_absolute() or not relative.parts or ".." in relative.parts or relative.parts[0].endswith(":"):
        raise RuntimeError(f"unsafe archive member: {name}")
    return relative


def digest(path: Path, algorithm: str) -> str:
    result = hashlib.new(algorithm)
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def sha256(path: Path) -> str:
    return digest(path, "sha256")


def checked_file(path: Path, spec: dict) -> None:
    if not path.is_file():
        raise RuntimeError(f"missing input: {path}")
    actual_size = path.stat().st_size
    actual_sha1 = digest(path, "sha1")
    actual_sha256 = sha256(path)
    expected_sha1 = spec["digests"]["upstreamPublished"]["sha1"]
    expected_sha256 = spec["digests"]["locallyDerived"]["sha256"]
    if actual_size != spec["size"] or actual_sha1 != expected_sha1 or actual_sha256 != expected_sha256:
        raise RuntimeError(f"upstream verification failed for {path.name}: size={actual_size}, sha1={actual_sha1}, sha256={actual_sha256}")


def download(config: dict, cache: Path) -> None:
    cache.mkdir(parents=True, exist_ok=True)
    for name, spec in config["upstream"].items():
        destination = cache / spec["fileName"]
        if destination.exists():
            try:
                checked_file(destination, spec)
                print(f"verified cached {destination.name}")
                continue
            except RuntimeError:
                destination.unlink()
        temporary = destination.with_suffix(destination.suffix + ".partial")
        request = urllib.request.Request(spec["url"], headers={"User-Agent": "NsisToolset reproducible builder"})
        last_error: Exception | None = None
        for attempt in range(1, 4):
            try:
                with urllib.request.urlopen(request, timeout=90) as response, temporary.open("wb") as output:
                    shutil.copyfileobj(response, output)
                checked_file(temporary, spec)
                temporary.replace(destination)
                print(f"downloaded and verified {name}: {destination.name}")
                last_error = None
                break
            except Exception as error:
                last_error = error
                temporary.unlink(missing_ok=True)
                if attempt < 3:
                    time.sleep(attempt * 2)
        if last_error:
            raise RuntimeError(f"failed to download {spec['url']}: {last_error}")


def _validated_zip_members(bundle: zipfile.ZipFile) -> None:
    for item in bundle.infolist():
        safe_archive_path(item.filename)


def safe_extract_zip(archive: Path, destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        _validated_zip_members(bundle)
        bundle.extractall(destination)
    roots = [path for path in destination.iterdir() if path.is_dir()]
    if len(roots) != 1:
        raise RuntimeError(f"expected one archive root, found {len(roots)}")
    return roots[0]


def safe_extract_zip_flat(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True)
    with zipfile.ZipFile(archive) as bundle:
        _validated_zip_members(bundle)
        bundle.extractall(destination)
