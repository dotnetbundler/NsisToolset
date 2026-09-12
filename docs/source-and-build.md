# Source and build record

The machine-readable source of truth is `config/upstream/3.12.json`. Each
Release also includes a generated `source-record.md`.

- Current toolset: `3.12-r1`
- Upstream NSIS: `3.12`
- `SOURCE_DATE_EPOCH`: `1776631488` (`2026-04-19T20:44:48Z`)

## Inputs

| File | Bytes | Published SHA-1 | Published MD5 | Local SHA-256 |
| --- | ---: | --- | --- | --- |
| `nsis-3.12.zip` | 2,362,938 | `364fd795b0cafc1fbff3e966f103a8f8fc8fb7f1` | `757c22153dd8b90f5e297310d9966997` | `56581f90db321581c5381193d796fffcf2d24b2f8fed2160a6c6a3baa67f2c4f` |
| `nsis-3.12-src.tar.bz2` | 1,818,389 | `432e99150881c061c7e313eb1aac45763d951572` | `8ec7c3e1228ac4eb96e5e421610b4aae` | `f3ed7a8e4aa2cf4e8cf47d3b563a02559e0cb4934db2662b2f9661b824e2b186` |

Downloads use the versioned NSIS 3.12 directory on SourceForge. Before
extraction, the build requires the byte size, published SHA-1, and local
SHA-256 to match. Published MD5 is recorded but is not an acceptance check.

## Build rules

- Native compilers use the official source without patches.
- `NSIS_CONFIG_CONST_DATA_PATH=no`; every host requires `NSISDIR=common`.
- Linux compilers are static and their GNU ABI notes are checked.
- macOS deployment targets are 10.13 for x64 and 11.0 for ARM64.
- SCons 4.8.1 is pinned by version and wheel hash.
- Native compilers are built twice on the same runner and compared byte for byte.
- Build details are written to `build-provenance.json`.

The Windows runtime is `Bin/makensis.exe` and `Bin/zlib1.dll` from the official
ZIP. The upstream root `makensis.exe` is only a launcher and is not used as the
host compiler.

The NSIS license is included as `common/COPYING`. Repository automation is
covered by the root `LICENSE`.
