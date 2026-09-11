# NsisToolset

NsisToolset is the production project for the complete, cross-host NSIS toolset consumed by `DotNet.Bundler.Nsis`. It intentionally contains no Bundler business logic. A Bundler release downloads one immutable toolset release while it is being produced, verifies it, and embeds it; an application developer neither installs NSIS nor downloads tools while packaging an application.

Current toolset version: **`3.12-r1`** (upstream `3.12`, packaging revision `r1`).

## Corrected design assumptions

`NSIS_CONFIG_CONST_DATA_PATH=no` makes a native compiler relocatable, but it derives its default data directory from the executable location. It cannot discover a separate top-level `common/` directory in this layout. Each host therefore has a small entry-point launcher that sets `NSISDIR` to `common/` and then executes the real compiler. Consumers must invoke the manifest's `entryPoint`, not guess the binary path.

The Windows ZIP contains two files named `makensis.exe`. The root 2.5-KiB file is only a launcher. The runtime uses `Bin/makensis.exe`, plus `Bin/zlib1.dll`. Linux compilers are fully static; macOS binaries may link only Apple system libraries. CI enforces these properties rather than assuming a single-file runtime.

## Release layout

```text
common/
  Include/ Plugins/ Stubs/ Contrib/
  nsisconf.nsh COPYING
hosts/
  win/          makensis.cmd makensis.exe zlib1.dll
  linux-x64/    makensis makensis.bin
  linux-arm64/  makensis makensis.bin
  osx-x64/      makensis makensis.bin
  osx-arm64/    makensis makensis.bin
build/hosts/     per-host build metadata
build-provenance.json
SOURCE-RECORD.md
toolset-manifest.json
```

`common/` is copied from the matching official standard ZIP and is not duplicated per host. `Plugins` contains Windows installer plug-ins used in generated installers; it is target data, not a host dependency.

Every file is inventoried with path, SHA-256, size, normalized Unix mode, and executable requirement. Every host record contains its RID, entry point, real binary, runtime files, and minimum-OS statement. ZIP readers do not consistently restore executable bits, so a consumer must verify every file and then apply `chmod` to records where `requiresExecutable` is `true` before invoking a Unix entry point.

## Build and verification

The workflow uses native GitHub-hosted runners: Ubuntu 24.04 x64/arm64, macOS 15 Intel/Apple Silicon, and Windows Server 2022. Native compilers use the upstream `install-compiler` target with all stubs, plug-ins, utilities, miscellaneous tools, and documentation skipped. Common installer data always comes from the exact matching official Windows ZIP.

Each native compiler is built twice on the same runner and the bytes must match. Every host then reports `v3.12`, compiles `fixtures/minimal.nsi` through the relocatable launcher, and uploads the resulting installer. Assembly verifies the complete declared file set, hashes, versions, permissions policy, host metadata, and relocation from a path containing spaces. A final Windows job runs all five host-generated installers, checks their installed marker, runs each uninstaller, and checks cleanup.

Linux uses a static userspace binary and checks its GNU ABI note (kernel 3.2 for x64, 3.7 for arm64). macOS uses deployment targets 10.13 (x64) and 11.0 (arm64). These are build baselines, while the precise CI-verified environments remain recorded in provenance. Windows Server 2022 is tested; this project does not assert an older Windows baseline beyond upstream's own compatibility.

Local checks that do not require all native operating systems:

```powershell
python scripts/toolset.py download --cache .cache/upstream
python scripts/toolset.py stage-windows --archive .cache/upstream/nsis-3.12.zip --stage stage --work artifacts/work
python -m unittest discover -s tests -v
```

Native production builds belong in CI so an emulated or cross-compiled Windows environment cannot masquerade as macOS. Full arguments, input hashes, and the no-patch policy are in [SOURCES.md](SOURCES.md).

## Release

Pushes and pull requests build and verify without publishing. A signed or annotated project tag exactly named `v3.12-r1` triggers publication only after install/uninstall validation. The release job uses `gh release create` without overwrite behavior, so an existing version is not silently replaced. Formal assets are:

- `nsis-toolset-3.12-r1.zip`
- `nsis-toolset-3.12-r1.zip.sha256`
- `toolset-manifest.json`
- `build-provenance.json`
- `source-record.md`

GitHub Actions artifacts are retained only for job-to-job transport. `DotNet.Bundler.Nsis` must consume the versioned GitHub Release asset, pin the asset SHA-256, validate the inner manifest, select exactly one host, apply recorded modes, and embed `common/` plus that host runtime. It must not use an Actions artifact or a `latest` URL.

## Upgrade procedure

1. Select a concrete upstream NSIS release and a new packaging revision.
2. Update both versioned URLs, byte sizes, SHA-256 values, and `SOURCE_DATE_EPOCH` in `config/toolset.json`, the workflow, and `SOURCES.md`.
3. Re-audit the standard ZIP layout, especially the real Windows compiler and all runtime dependencies.
4. Review upstream build flags and the `Source/exehead/config.h` compatibility contract. Common data and native compiler sources must match exactly.
5. Run the entire native matrix, reproducibility comparisons, relocation tests, and all-host Windows installation tests.
6. Review upstream license changes, update both READMEs, tag the exact toolset version, and let the protected release workflow publish once.

## Trust and licensing

Downloads are accepted only when both recorded size and SHA-256 match. Extraction rejects path traversal. Actions and the SCons wheel are commit/hash pinned. See [SOURCES.md](SOURCES.md) for source and build facts. Repository automation is MIT-licensed; redistributed NSIS content retains upstream `COPYING` inside every toolset.
