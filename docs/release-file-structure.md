# Release file structure

This document describes the assets uploaded by the project to GitHub Releases and the directory layout inside the toolset ZIP.

## Release assets

```text
nsis-toolset-<version>.zip          # Runtime files for all supported hosts
nsis-toolset-<version>.zip.sha256   # SHA-256 checksum for the ZIP
```

`<version>` is the toolset version in the form `<upstream-version>-<local-label>`, for example `3.12-r1`, with the Release tag `v3.12-r1`. The checksum file contains one line: `<SHA-256>  nsis-toolset-<version>.zip`.

## ZIP contents

These paths are directly at the ZIP root, with no enclosing version directory. `...` represents directory contents retained from the official Windows ZIP; individual files vary with the upstream NSIS version.

```text
nsis-toolset-<version>.zip
├── makensis.cmd             # Windows root launcher; runs hosts/win-x86/makensis.exe
├── makensis                 # Linux/macOS root launcher; selects the compiler for the host OS and architecture
├── common/                  # NSIS data shared by all hosts
│   ├── Contrib/             # NSIS components and resources, including UI and language files
│   │   └── ...
│   ├── Include/             # NSIS script include files
│   │   └── ...
│   ├── Plugins/             # Plugins for generated Windows installers
│   │   └── ...
│   ├── Stubs/               # Stub binaries used to generate Windows installers
│   │   └── ...
│   ├── nsisconf.nsh         # Default NSIS configuration
│   └── COPYING              # Bundled NSIS license
└── hosts/                   # Compilers grouped by host OS and architecture
    ├── win-x86/             # Windows x86 runtime files
    │   ├── makensis.exe     # Windows NSIS compiler
    │   └── zlib1.dll        # zlib DLL required by the Windows compiler
    ├── linux-x64/           # Linux x64 runtime files
    │   └── makensis         # Linux x64 NSIS compiler
    ├── linux-arm64/         # Linux ARM64 runtime files
    │   └── makensis         # Linux ARM64 NSIS compiler
    ├── osx-x64/             # macOS x64 runtime files
    │   └── makensis         # macOS x64 NSIS compiler
    └── osx-arm64/           # macOS ARM64 runtime files
        └── makensis         # macOS ARM64 NSIS compiler
```

Both root launchers set `NSISDIR` to the shared `common/` directory. Keep the directory layout intact and compile scripts through the root launcher; see the [README](../README.md) for commands.
