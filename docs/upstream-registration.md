# Registering an upstream NSIS release

Use this procedure when adding a new upstream NSIS version. Packaging labels do
not require new upstream files.

## Configuration model

Store exactly one configuration file for each upstream NSIS version:

```text
config/upstream/<upstream-version>.json
```

For example, both `v3.12-r1` and `v3.12-preview.2` use
`config/upstream/3.12.json`. The local labels `r1` and `preview.2` distinguish
toolset releases; they do not describe different upstream archives.

## Required source facts

Before running a registration tool:

1. Copy the Windows archive SHA-1 and MD5 from its SourceForge file information
   page.
2. Copy the source archive SHA-1 and MD5 from its SourceForge file information
   page.
3. Obtain `SOURCE_DATE_EPOCH` from the official source archive's UTC release
   time.

These values are explicit inputs so a checksum calculated from a new download
is never misrepresented as an upstream-published checksum.

## Register on Windows

Run from Command Prompt:

```bat
tools\register-upstream.cmd 3.12 1776631488 WINDOWS_SHA1 SOURCE_SHA1 WINDOWS_MD5 SOURCE_MD5
```

The Windows tool uses the in-box `curl.exe` and `certutil.exe`; it does not use
Python, Node.js, PowerShell, or .NET.

## Register on Linux or macOS

Run with the system shell:

```sh
sh tools/register-upstream.sh 3.12 1776631488 WINDOWS_SHA1 SOURCE_SHA1 WINDOWS_MD5 SOURCE_MD5
```

The POSIX tool uses the system `curl` and checksum commands. It supports GNU
`sha*sum` as well as the macOS `shasum` and `md5` tools. It does not use Python,
Node.js, or .NET.

## Retain downloads for inspection

Both tools normally remove downloaded archives after completion or failure. To
keep them under `.cache/upstream/<version>`, append `--keep-downloads`:

```bat
tools\register-upstream.cmd 3.12 1776631488 WINDOWS_SHA1 SOURCE_SHA1 WINDOWS_MD5 SOURCE_MD5 --keep-downloads
```

```sh
sh tools/register-upstream.sh 3.12 1776631488 WINDOWS_SHA1 SOURCE_SHA1 WINDOWS_MD5 SOURCE_MD5 --keep-downloads
```

An explicit retention directory may follow the option:

```bat
tools\register-upstream.cmd 3.12 1776631488 WINDOWS_SHA1 SOURCE_SHA1 WINDOWS_MD5 SOURCE_MD5 --keep-downloads C:\temp\nsis-3.12
```

```sh
sh tools/register-upstream.sh 3.12 1776631488 WINDOWS_SHA1 SOURCE_SHA1 WINDOWS_MD5 SOURCE_MD5 --keep-downloads /tmp/nsis-3.12
```

## Review the result

The tools download the official Windows and source archives, require the given
SHA-1 and MD5 values to match, calculate SHA-256 and byte sizes locally, and
write `config/upstream/<version>.json`. They never overwrite an existing
configuration.

Before committing the new file:

1. Compare its URLs, sizes, and published digests with the upstream pages.
2. Confirm the filename matches its `upstreamVersion` value.
3. Review the standard ZIP layout and Windows runtime dependencies.
4. Review upstream source/build changes and licenses.
5. Run the full native matrix and release validation described in the
   [build and release guide](build-and-release.md).
