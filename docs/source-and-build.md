# Source and build record

This repository record documents the currently audited upstream inputs and
native build policy. `config/upstream/3.12.json` is the machine-readable source
of truth used by automation. Each release also publishes a generated
`source-record.md` containing the values used for that specific build.

Toolset revision: `3.12-r1`  
Upstream release: NSIS `3.12`  
Reproducible timestamp (`SOURCE_DATE_EPOCH`): `1776631488`
(`2026-04-19T20:44:48Z`)

## Upstream inputs

| Input | Official URL | Bytes | Upstream-published SHA-1 | Upstream-published MD5 | Locally-derived SHA-256 |
| --- | --- | ---: | --- | --- | --- |
| `nsis-3.12.zip` | <https://sourceforge.net/projects/nsis/files/NSIS%203/3.12/nsis-3.12.zip/download> | 2,362,938 | `364fd795b0cafc1fbff3e966f103a8f8fc8fb7f1` | `757c22153dd8b90f5e297310d9966997` | `56581f90db321581c5381193d796fffcf2d24b2f8fed2160a6c6a3baa67f2c4f` |
| `nsis-3.12-src.tar.bz2` | <https://sourceforge.net/projects/nsis/files/NSIS%203/3.12/nsis-3.12-src.tar.bz2/download> | 1,818,389 | `432e99150881c061c7e313eb1aac45763d951572` | `8ec7c3e1228ac4eb96e5e421610b4aae` | `f3ed7a8e4aa2cf4e8cf47d3b563a02559e0cb4934db2662b2f9661b824e2b186` |

These are versioned SourceForge release URLs rather than `latest` aliases.
SourceForge publishes SHA-1 and MD5 for the files. This project independently
calculates SHA-256 from bytes downloaded through those official URLs and does
not represent SHA-256 as an upstream-published value.

Before extraction, automation requires the recorded byte size,
upstream-published SHA-1, and locally-derived SHA-256 to match. MD5 is retained
as an upstream source-consistency record but is not an acceptance check.

## Native compiler build

Linux and macOS builds use the official source archive without patches. Every
host build record therefore contains an empty `patches` array. The effective
SCons parameters are:

```text
VERSION=3.12 VER_MAJOR=3 VER_MINOR=12 VER_REVISION=0 VER_BUILD=0
SOURCE_DATE_EPOCH=1776631488 NSIS_CONFIG_CONST_DATA_PATH=no
SKIPSTUBS=all SKIPPLUGINS=all SKIPUTILS=all SKIPMISC=all SKIPDOC=all
PREFIX=<artifacts-native-install-root> install-compiler
```

Linux additionally uses `APPEND_LINKFLAGS=-static`; CI rejects a dynamic ELF
and checks its GNU ABI note. macOS uses deployment targets 10.13 for x64 and
11.0 for ARM64; CI rejects dependencies outside Apple system libraries.

SCons is locked to 4.8.1 by version and wheel hash. Compiler, runner image,
dependency, binary format, build parameters, output size, and output hash are
captured in `build-provenance.json`.

The common data and Windows runtime come from the verified standard ZIP. The
upstream root `makensis.exe` is deliberately ignored because it is a launcher.
`Bin/makensis.exe` and `Bin/zlib1.dll` form the shipped Windows runtime. Setup,
log, and `strlen_8192` variants are not build inputs.

`NSIS_CONFIG_CONST_DATA_PATH=no` makes each native compiler relocatable, but it
does not make the compiler discover the separate top-level `common/` directory.
The manifest therefore declares `NSISDIR=common` as required environment for
every host.

## Licenses

The release archive preserves the NSIS license verbatim at `common/COPYING`.
This repository's original automation is MIT-licensed; see the root `LICENSE`.
Consumers must retain and comply with upstream notices when redistributing NSIS
files.
