# Source and build policy

The machine-readable source of truth for each upstream NSIS version is
`config/upstream/<version>.json`. Adding a version requires one new upstream
config; this document is not copied or rewritten for each version.

Every release includes a generated `source-record.md` containing its exact
toolset version, upstream version, `SOURCE_DATE_EPOCH`, archive URLs, sizes, and
digests.

## Generated source record

`source-record.md` is not stored in the repository and is not created by the
upstream registration scripts. The `assemble` command generates it from the
selected `config/upstream/<version>.json` after all host and installer smoke
tests pass:

1. `packaging.write_source_record` writes `stage/SOURCE-RECORD.md`.
2. The staged uppercase file is included inside the toolset ZIP and covered by
   `toolset-manifest.json`.
3. `release_tasks.assemble` also copies the same content to
   `artifacts/dist/source-record.md` as a standalone release asset.

The file therefore exists only after a successful assemble run. Tag workflows
publish the standalone copy together with the ZIP and the other release assets.

## Source acceptance

Each upstream config records the official Windows ZIP and source archive. A
download is accepted only when its byte size, upstream-published SHA-1, and
locally derived SHA-256 match the config. Upstream-published MD5 is retained as
an additional record but is not an acceptance check.

Register new upstream versions with
[upstream-registration.md](upstream-registration.md).

## Build rules

- Native compilers use the official source without patches.
- `NSIS_CONFIG_CONST_DATA_PATH=no`; every host requires `NSISDIR=common`.
- Linux compilers are static and their GNU ABI notes are checked.
- macOS deployment targets are 10.13 for x64 and 11.0 for ARM64.
- SCons is pinned by version and wheel hash in `requirements-build.txt`.
- Native compilers are built twice on the same runner and compared byte for byte.
- Build details are written to `build-provenance.json`.

The Windows runtime comes from `Bin/makensis.exe` and `Bin/zlib1.dll` in the
verified official Windows ZIP. The upstream root `makensis.exe` is only a
launcher and is not used as the host compiler.

The NSIS license is included as `common/COPYING`. Repository automation is
covered by the root `LICENSE`.
