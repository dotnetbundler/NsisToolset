# Register an upstream NSIS release

Create one config for each upstream NSIS version:

```text
config/upstream/<version>.json
```

Local labels share that config. For example, `v3.12-r1` and
`v3.12-preview.2` both use `config/upstream/3.12.json`.

## Get the required values

Open the NSIS version directory on SourceForge:

```text
https://sourceforge.net/projects/nsis/files/NSIS%203/<version>/
```

For version `3.12`, use:

<https://sourceforge.net/projects/nsis/files/NSIS%203/3.12/>

SourceForge documents that SHA1 and MD5 are shown by clicking the information
icon beside a file:

<https://sourceforge.net/p/forge/documentation/Verifying%20downloaded%20files/>

Collect these values:

| Argument | How to get it |
| --- | --- |
| `VERSION` | NSIS version, for example `3.12` |
| `SOURCE_DATE_EPOCH` | Source archive's UTC modified time, formatted as `YYYY-MM-DD HH:MM:SS UTC`; the script converts it to Unix seconds |
| `WINDOWS_SHA1` | Click the information icon for `nsis-<version>.zip`; copy SHA1 |
| `WINDOWS_MD5` | From the same information panel; copy MD5 |
| `SOURCE_SHA1` | Click the information icon for `nsis-<version>-src.tar.bz2`; copy SHA1 |
| `SOURCE_MD5` | From the same information panel; copy MD5 |

SHA-1 values contain 40 hexadecimal characters. MD5 values contain 32.
Do not calculate these four values yourself: they must be copied from the
upstream record. The scripts calculate SHA-256 and file sizes after downloading.

For example, pass `2026-04-19 20:44:48 UTC` to produce the JSON value
`1776631488`.

## Run the tool

Windows Command Prompt:

```bat
tools\register-upstream.cmd VERSION "SOURCE_DATE_EPOCH" WINDOWS_SHA1 WINDOWS_MD5 SOURCE_SHA1 SOURCE_MD5
```

Linux or macOS:

```sh
sh tools/register-upstream.sh VERSION "SOURCE_DATE_EPOCH" WINDOWS_SHA1 WINDOWS_MD5 SOURCE_SHA1 SOURCE_MD5
```

The tool downloads both archives, verifies the supplied SHA-1 and MD5 values,
calculates SHA-256 and sizes, and writes `config/upstream/<version>.json`. It
refuses to overwrite an existing config.

Downloads are deleted by default. To keep them:

```text
--keep-downloads [directory]
```

Without a directory, files are kept under `.cache/upstream/<version>`.

## Review

Before committing the config, check its version, filenames, URLs, sizes,
digests, and `SOURCE_DATE_EPOCH`. Then run the full workflow for the new
upstream version.
