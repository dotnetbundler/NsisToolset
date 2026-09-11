#!/bin/sh
set -eu

usage() {
  echo "usage: $0 <version> <source-date-epoch> <windows-sha1> <source-sha1> <windows-md5> <source-md5> [--keep-downloads [directory]]" >&2
  exit 2
}

[ "$#" -ge 6 ] && [ "$#" -le 8 ] || usage
version=$1
epoch=$2
windows_sha1=$3
source_sha1=$4
windows_md5=$5
source_md5=$6
keep_downloads=false
download_directory=
if [ "$#" -ge 7 ]; then
  [ "$7" = "--keep-downloads" ] || usage
  keep_downloads=true
  if [ "$#" -eq 8 ]; then
    download_directory=$8
  fi
fi

echo "[1/7] Validating arguments and required system commands"
printf '%s\n' "$version" | grep -Eq '^[0-9]+(\.[0-9]+){1,3}$' || {
  echo "version must be a numeric NSIS version such as 3.12 or 3.06.1" >&2
  exit 2
}
printf '%s\n' "$epoch" | grep -Eq '^[0-9]+$' || {
  echo "source-date-epoch must be an integer" >&2
  exit 2
}
for value in "$windows_sha1" "$source_sha1"; do
  printf '%s\n' "$value" | grep -Eqi '^[0-9a-f]{40}$' || {
    echo "each SHA-1 must contain exactly 40 hexadecimal characters" >&2
    exit 2
  }
done
for value in "$windows_md5" "$source_md5"; do
  printf '%s\n' "$value" | grep -Eqi '^[0-9a-f]{32}$' || {
    echo "each MD5 must contain exactly 32 hexadecimal characters" >&2
    exit 2
  }
done

for command_name in curl mktemp grep tr wc awk; do
  command -v "$command_name" >/dev/null 2>&1 || {
    echo "required system command not found: $command_name" >&2
    exit 1
  }
done

hash_file() {
  algorithm=$1
  file=$2
  case "$algorithm" in
    sha1)
      if command -v sha1sum >/dev/null 2>&1; then sha1sum "$file" | awk '{print $1}'
      else shasum -a 1 "$file" | awk '{print $1}'; fi
      ;;
    sha256)
      if command -v sha256sum >/dev/null 2>&1; then sha256sum "$file" | awk '{print $1}'
      else shasum -a 256 "$file" | awk '{print $1}'; fi
      ;;
    md5)
      if command -v md5sum >/dev/null 2>&1; then md5sum "$file" | awk '{print $1}'
      else md5 -q "$file"; fi
      ;;
  esac
}

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
output="$repo_root/config/upstream/$version.json"
[ ! -e "$output" ] || {
  echo "refusing to overwrite existing config: $output" >&2
  exit 1
}

echo "[2/7] Preparing the download directory"
if [ "$keep_downloads" = true ]; then
  if [ -n "$download_directory" ]; then
    work=$download_directory
  else
    work="$repo_root/.cache/upstream/$version"
  fi
  mkdir -p "$work"
  cleanup=false
else
  work=$(mktemp -d "${TMPDIR:-/tmp}/nsis-upstream.XXXXXX")
  cleanup=true
fi
if [ "$cleanup" = true ]; then
  trap 'rm -rf "$work"' EXIT HUP INT TERM
fi
echo "Download directory: $work"

windows_name="nsis-$version.zip"
source_name="nsis-$version-src.tar.bz2"
base_url="https://sourceforge.net/projects/nsis/files/NSIS%203/$version"
windows_url="$base_url/$windows_name/download"
source_url="$base_url/$source_name/download"
windows_file="$work/$windows_name"
source_file="$work/$source_name"

echo "[3/7] Downloading the Windows archive"
curl -fL --retry 2 --output "$windows_file" "$windows_url"
echo "[4/7] Downloading the source archive"
curl -fL --retry 2 --output "$source_file" "$source_url"

echo "[5/7] Verifying the published SHA-1 and MD5 values"
actual_windows_sha1=$(hash_file sha1 "$windows_file" | tr 'A-F' 'a-f')
actual_source_sha1=$(hash_file sha1 "$source_file" | tr 'A-F' 'a-f')
[ "$actual_windows_sha1" = "$(printf '%s' "$windows_sha1" | tr 'A-F' 'a-f')" ] || {
  echo "Windows archive does not match the upstream-published SHA-1" >&2; exit 1;
}
[ "$actual_source_sha1" = "$(printf '%s' "$source_sha1" | tr 'A-F' 'a-f')" ] || {
  echo "source archive does not match the upstream-published SHA-1" >&2; exit 1;
}
[ "$(hash_file md5 "$windows_file" | tr 'A-F' 'a-f')" = "$(printf '%s' "$windows_md5" | tr 'A-F' 'a-f')" ] || {
  echo "Windows archive MD5 differs from the published record" >&2; exit 1;
}
[ "$(hash_file md5 "$source_file" | tr 'A-F' 'a-f')" = "$(printf '%s' "$source_md5" | tr 'A-F' 'a-f')" ] || {
  echo "source archive MD5 differs from the published record" >&2; exit 1;
}

echo "Published checksums match."
echo "[6/7] Calculating SHA-256 values and archive sizes"
windows_sha256=$(hash_file sha256 "$windows_file" | tr 'A-F' 'a-f')
source_sha256=$(hash_file sha256 "$source_file" | tr 'A-F' 'a-f')
windows_size=$(wc -c <"$windows_file" | tr -d ' ')
source_size=$(wc -c <"$source_file" | tr -d ' ')
mkdir -p "$(dirname "$output")"

echo "[7/7] Writing the upstream configuration"
cat >"$output" <<EOF
{
  "schemaVersion": 1,
  "upstreamVersion": "$version",
  "sourceDateEpoch": $epoch,
  "upstream": {
    "windowsZip": {
      "fileName": "$windows_name",
      "url": "$windows_url",
      "size": $windows_size,
      "digests": {
        "upstreamPublished": { "sha1": "$actual_windows_sha1", "md5": "$windows_md5" },
        "locallyDerived": { "sha256": "$windows_sha256" }
      }
    },
    "sourceArchive": {
      "fileName": "$source_name",
      "url": "$source_url",
      "size": $source_size,
      "digests": {
        "upstreamPublished": { "sha1": "$actual_source_sha1", "md5": "$source_md5" },
        "locallyDerived": { "sha256": "$source_sha256" }
      }
    }
  }
}
EOF

echo "wrote $output"
echo "review the new file before committing it"
if [ "$cleanup" = true ]; then
  echo "Downloaded files deleted (default)."
else
  echo "Downloaded files retained at: $work"
fi
