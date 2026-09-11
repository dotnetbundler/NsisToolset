# NsisToolset

NsisToolset is an independent production and release project for a complete, cross-host NSIS toolset. Any build tool, framework, CI system, or individual can download a versioned release, verify its manifest, select a host runtime, and use it without installing NSIS. The repository contains no downstream product or bundler business logic.

Current toolset version: **`3.12-r1`** (upstream `3.12`, packaging revision `r1`).

## Corrected design assumptions

`NSIS_CONFIG_CONST_DATA_PATH=no` makes a native compiler relocatable, but it derives its default data directory from the executable location. It cannot discover the separate top-level `common/` directory used to avoid host duplication. Every host record therefore declares the real `binary`, a required `NSISDIR` environment value expressed as a toolset-relative path (`common`), and an optional `convenienceLauncher` that sets it before starting the compiler.

Programmatic consumers should resolve `binary` and `requiredEnvironment` against the extracted toolset root and launch the binary directly. This avoids requiring a command processor or shell and is especially important on Windows, where starting a `.cmd` file is less convenient and less explicit than starting an executable. Human command-line users may run the convenience launcher instead.

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

Every file is inventoried with path, SHA-256, size, normalized Unix mode, and executable requirement. Every host record contains its RID, real binary, required environment, optional launcher, runtime files, and minimum-OS statement. ZIP readers do not consistently restore executable bits, so a consumer must verify every file and then apply `chmod` to records where `requiresExecutable` is `true` before invoking a Unix binary or launcher.

## Build and verification

The workflow uses native GitHub-hosted runners: Ubuntu 24.04 x64/arm64, macOS 15 Intel/Apple Silicon, and Windows Server 2022. Native compilers use the upstream `install-compiler` target with all stubs, plug-ins, utilities, miscellaneous tools, and documentation skipped. Common installer data always comes from the exact matching official Windows ZIP.

Each native compiler is built twice on the same runner and the bytes must match. Every host then reports `v3.12`, compiles `fixtures/minimal.nsi` by launching the real binary with the declared environment, and also checks the optional launcher. Assembly verifies the complete declared file set, hashes, versions, permissions policy, host metadata, and relocation from a path containing spaces. A final Windows job runs all five host-generated installers, checks their installed marker, runs each uninstaller, and checks cleanup.

## Python files in this repository

- `scripts/toolset.py` downloads and verifies upstream inputs, stages hosts, generates and verifies the manifest, and creates the deterministic ZIP.
- `scripts/host_metadata.py` records native compiler, runner, toolchain, dependency, and build facts.
- `scripts/provenance.py` combines per-host facts with GitHub Actions provenance.
- `tests/test_toolset.py` tests integrity failures, deterministic packaging, path safety, permission metadata, and the host invocation contract.

These files are production automation only. They are not copied into the released NSIS toolset and are not downstream runtime dependencies. Python is used because the same assembly logic must run on Windows, Linux, and macOS, and NSIS's own SCons source build already requires Python.

Linux uses a static userspace binary and checks its GNU ABI note (kernel 3.2 for x64, 3.7 for arm64). macOS uses deployment targets 10.13 (x64) and 11.0 (arm64). These are build baselines, while the precise CI-verified environments remain recorded in provenance. Windows Server 2022 is tested; this project does not assert an older Windows baseline beyond upstream's own compatibility.

Local checks that do not require all native operating systems:

```powershell
python scripts/toolset.py download --cache .cache/upstream
python scripts/toolset.py stage-windows --archive .cache/upstream/nsis-3.12.zip --stage stage --work artifacts/work
python -m unittest discover -s tests -v
```

Native production builds belong in CI so an emulated or cross-compiled Windows environment cannot masquerade as macOS. Full arguments, input hashes, and the no-patch policy are in [SOURCES.md](SOURCES.md).

## Release

Pushes and pull requests build and verify without publishing. A project tag exactly named `v3.12-r1` triggers publication only after install/uninstall validation. The release job uses `gh release create` without overwrite behavior, so an existing version is not silently replaced. Formal assets are:

- `nsis-toolset-3.12-r1.zip`
- `nsis-toolset-3.12-r1.zip.sha256`
- `toolset-manifest.json`
- `build-provenance.json`
- `source-record.md`

GitHub Actions artifacts are retained only for job-to-job transport. Consumers must use the versioned GitHub Release asset, pin the asset SHA-256, validate the inner manifest, select exactly one host, apply recorded modes, set the declared environment, and distribute or invoke `common/` plus that host runtime. They must not use an Actions artifact or a `latest` URL. `DotNet.Bundler.Nsis` is one possible consumer, not a privileged or defining one.

## Upgrade procedure

1. Select a concrete upstream NSIS release and a new packaging revision.
2. Update both versioned URLs, byte sizes, upstream-published digests, locally-derived SHA-256 values, and `SOURCE_DATE_EPOCH` in `config/toolset.json`, the workflow, and `SOURCES.md`.
3. Re-audit the standard ZIP layout, especially the real Windows compiler and all runtime dependencies.
4. Review upstream build flags and the `Source/exehead/config.h` compatibility contract. Common data and native compiler sources must match exactly.
5. Run the entire native matrix, reproducibility comparisons, relocation tests, and all-host Windows installation tests.
6. Review upstream license changes, update both READMEs, tag the exact toolset version, and let the protected release workflow publish once.

## Trust and licensing

SourceForge publishes SHA-1 and MD5 for both upstream archives. This project independently derives SHA-256 from the downloaded bytes; it does not attribute SHA-256 publication to upstream. Downloads are accepted only when size, upstream-published SHA-1, and locally-derived SHA-256 all match. MD5 is recorded for source consistency, not used as a security check. Extraction rejects path traversal. Actions and the SCons wheel are commit/hash pinned. See [SOURCES.md](SOURCES.md) for exact values and build facts. Repository automation is MIT-licensed; redistributed NSIS content retains upstream `COPYING` inside every toolset.

- Windows ZIP — published SHA-1 `364fd795b0cafc1fbff3e966f103a8f8fc8fb7f1`, published MD5 `757c22153dd8b90f5e297310d9966997`, derived SHA-256 `56581f90db321581c5381193d796fffcf2d24b2f8fed2160a6c6a3baa67f2c4f`.
- Source archive — published SHA-1 `432e99150881c061c7e313eb1aac45763d951572`, published MD5 `8ec7c3e1228ac4eb96e5e421610b4aae`, derived SHA-256 `f3ed7a8e4aa2cf4e8cf47d3b563a02559e0cb4934db2662b2f9661b824e2b186`.
