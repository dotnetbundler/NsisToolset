#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 5 ]]; then
  echo "usage: $0 <source-archive> <output-dir> <rid> <source-date-epoch> <upstream-version>" >&2
  exit 2
fi

archive=$1
output=$2
rid=$3
epoch=$4
upstream_version=$5
IFS=. read -r version_major version_minor version_revision version_build version_extra <<<"$upstream_version"
if [[ -n "${version_extra:-}" || -z "${version_major:-}" || -z "${version_minor:-}" ]]; then
  echo "unsupported NSIS numeric version: $upstream_version" >&2
  exit 2
fi
version_revision=${version_revision:-0}
version_build=${version_build:-0}
work="${RUNNER_TEMP:-/tmp}/nsis-build-${rid}"
rm -rf "$work"
mkdir -p "$work/src" "$work/install" "$output"
tar -xjf "$archive" -C "$work/src" --strip-components=1

export SOURCE_DATE_EPOCH="$epoch"
common_args=(
  -C "$work/src"
  -j2
  VERSION="$upstream_version"
  VER_MAJOR="$version_major"
  VER_MINOR="$version_minor"
  VER_REVISION="$version_revision"
  VER_BUILD="$version_build"
  SOURCE_DATE_EPOCH="$epoch"
  NSIS_CONFIG_CONST_DATA_PATH=no
  PREFIX="$work/install"
  SKIPSTUBS=all
  SKIPPLUGINS=all
  SKIPUTILS=all
  SKIPMISC=all
  SKIPDOC=all
)

case "$rid" in
  linux-x64|linux-arm64)
    # A fully static binary avoids silently depending on a runner-specific libz,
    # libstdc++, or glibc. The CI dependency audit below enforces this claim.
    scons "${common_args[@]}" APPEND_LINKFLAGS=-static install-compiler
    ;;
  osx-x64)
    export MACOSX_DEPLOYMENT_TARGET=10.13
    scons "${common_args[@]}" APPEND_CCFLAGS="-mmacosx-version-min=10.13" APPEND_LINKFLAGS="-mmacosx-version-min=10.13" install-compiler
    ;;
  osx-arm64)
    export MACOSX_DEPLOYMENT_TARGET=11.0
    scons "${common_args[@]}" APPEND_CCFLAGS="-mmacosx-version-min=11.0" APPEND_LINKFLAGS="-mmacosx-version-min=11.0" install-compiler
    ;;
  *) echo "unsupported RID: $rid" >&2; exit 2 ;;
esac

cp "$work/install/makensis" "$output/makensis"
chmod 0755 "$output/makensis"

"$output/makensis" -VERSION | tee "$output/version.txt"
grep -Fx "v$upstream_version" "$output/version.txt"

case "$rid" in
  linux-*)
    file "$output/makensis" | tee "$output/file.txt"
    readelf --notes "$output/makensis" | tee "$output/elf-notes.txt"
    ldd_output=$(ldd "$output/makensis" 2>&1 || true)
    printf '%s\n' "$ldd_output" | tee "$output/dependencies.txt"
    if ! grep -Eq 'not a dynamic executable|statically linked' "$output/dependencies.txt"; then
      echo "Linux makensis must be fully static" >&2
      exit 1
    fi
    expected_abi=3.2.0
    [[ "$rid" == linux-arm64 ]] && expected_abi=3.7.0
    if ! grep -Fq "ABI: $expected_abi" "$output/elf-notes.txt"; then
      echo "ELF GNU ABI note does not prove the configured Linux baseline $expected_abi" >&2
      exit 1
    fi
    ;;
  osx-*)
    file "$output/makensis" | tee "$output/file.txt"
    otool -L "$output/makensis" | tee "$output/dependencies.txt"
    if tail -n +2 "$output/dependencies.txt" | sed 's/^[[:space:]]*//' | grep -Ev '^(/usr/lib/|/System/Library/)' | grep -q .; then
      echo "macOS makensis has a non-system dynamic dependency" >&2
      exit 1
    fi
    ;;
esac

python3 "$(cd "$(dirname "$0")" && pwd)/host_metadata.py" \
  --rid "$rid" --binary "$output/makensis" --version-file "$output/version.txt" \
  --upstream-version "$upstream_version" --source-date-epoch "$epoch" \
  --file-report "$output/file.txt" --dependencies "$output/dependencies.txt" \
  --output "$output/build-metadata.json"
