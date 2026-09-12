# NsisToolset

[简体中文](README.zh-CN.md)

NsisToolset produces a versioned, relocatable NSIS toolset for Windows, Linux,
and macOS build hosts. It contains the shared NSIS installer data, one compiler
runtime per supported host, root launchers, and machine-readable integrity and
host metadata. Consumers do not need a system-wide NSIS installation.

Current toolset version: **`3.12-r1`** (upstream NSIS `3.12`, local label
`r1`).

## Supported hosts

| Toolset RID | Build host | Compiler |
| --- | --- | --- |
| `win-x86` | Windows x86, x64, or ARM64 through x86 compatibility | Official upstream PE x86 compiler |
| `linux-x64` | Linux x64 | Native static compiler |
| `linux-arm64` | Linux ARM64 | Native static compiler |
| `osx-x64` | macOS Intel | Native compiler |
| `osx-arm64` | macOS Apple Silicon | Native compiler |

Windows ARM64 support is compatibility through Windows x86 emulation, not a
native ARM64 compiler.

## Quick start

Download the versioned ZIP and its `.sha256` file from the matching GitHub
Release. Verify the outer ZIP checksum, extract it, and invoke the root launcher:

```powershell
.\makensis.cmd path\to\installer.nsi
```

```sh
chmod +x makensis hosts/*/makensis
./makensis path/to/installer.nsi
```

The root launchers set `NSISDIR` to the bundled `common/` directory. Programs
embedding the toolset should instead read `toolset-manifest.json`, select a
compatible host record, resolve its `binary` and `requiredEnvironment` values
against the extracted root, restore declared executable modes, and invoke that
binary directly.

See the [consumer guide](docs/consumer-guide.md) for the release layout,
integrity checks, host-selection contract, and asset meanings.

## Build and release

Only a pushed version tag or a manual workflow dispatch starts a build. Version
tags have the form `v<registered-upstream>-<local-label>`, such as `v3.12-r1`
or `v3.12-preview.2`. Manual dispatch performs the complete build and validation
without publishing a GitHub Release.

The pipeline downloads each upstream archive once, builds four native hosts,
tests all five generated installers on Windows, assembles the release on Linux,
and requires repeated builds and packages to be byte-identical where specified.

- [Build and release guide](docs/build-and-release.md)
- [Upstream registration](docs/upstream-registration.md)
- [Source and build record](docs/source-and-build.md)

Run the repository unit tests locally with:

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
python -m unittest discover -s tests -v
```

Repository automation is MIT-licensed. Redistributed NSIS content retains the
upstream license in `common/COPYING` inside every toolset archive.
