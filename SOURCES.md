# Source and build record

Toolset revision: `3.12-r1`  
Upstream release: NSIS `3.12`  
Reproducible timestamp (`SOURCE_DATE_EPOCH`): `1776631488` (`2026-04-19T20:44:48Z`)

| Input | Official URL | Bytes | SHA-256 |
|---|---|---:|---|
| `nsis-3.12.zip` | <https://sourceforge.net/projects/nsis/files/NSIS%203/3.12/nsis-3.12.zip/download> | 2,362,938 | `56581f90db321581c5381193d796fffcf2d24b2f8fed2160a6c6a3baa67f2c4f` |
| `nsis-3.12-src.tar.bz2` | <https://sourceforge.net/projects/nsis/files/NSIS%203/3.12/nsis-3.12-src.tar.bz2/download> | 1,818,389 | `f3ed7a8e4aa2cf4e8cf47d3b563a02559e0cb4934db2662b2f9661b824e2b186` |

The URLs are versioned SourceForge release URLs, not `latest` aliases. Redirects are allowed, but the downloaded bytes must match both the recorded size and SHA-256 before extraction.

## Native compiler build

Linux and macOS builds use the official source archive without patches. `patches` is therefore an empty array in every host build record. The effective SCons parameters are:

```text
VERSION=3.12 VER_MAJOR=3 VER_MINOR=12 VER_REVISION=0 VER_BUILD=0
SOURCE_DATE_EPOCH=1776631488 NSIS_CONFIG_CONST_DATA_PATH=no
SKIPSTUBS=all SKIPPLUGINS=all SKIPUTILS=all SKIPMISC=all SKIPDOC=all
PREFIX=<temporary-install-root> install-compiler
```

Linux additionally uses `APPEND_LINKFLAGS=-static`; CI rejects a dynamic ELF. macOS uses deployment targets 10.13 for x64 and 11.0 for arm64, and CI rejects non-system dynamic dependencies. SCons is locked to 4.8.1 by version and wheel hash. Compiler, runner-image, dependency, binary-format, build-parameter, output-size, and output-hash facts are captured in `build-provenance.json`.

The common data and Windows runtime are copied from the verified standard ZIP. The root `makensis.exe` is deliberately ignored because it is a launcher. `Bin/makensis.exe` and its required `Bin/zlib1.dll` form the Windows runtime. Setup, log, and `strlen_8192` variants are not inputs.

## Licenses

NSIS licensing is preserved verbatim as `common/COPYING` in the release archive. This repository's original automation is MIT-licensed; see `LICENSE`. Consumers must retain and comply with upstream notices for redistributed NSIS files.

