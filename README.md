# NsisToolset

[简体中文](README.zh-CN.md)

NsisToolset packages NSIS as a versioned, relocatable toolset for Windows,
Linux, and macOS build hosts. No system-wide NSIS installation is required.

Example version: **`3.12-r1`** (NSIS `3.12`, revised version `r1`).

## Use

Download the versioned ZIP and `.sha256` file from the matching GitHub Release.
Verify the checksum, extract the ZIP, and run the root launcher:

```powershell
.\makensis.cmd path\to\installer.nsi
```

```sh
# Run this only if the extractor did not preserve executable permissions.
chmod +x makensis hosts/*/makensis
./makensis path/to/installer.nsi
```

Supported toolset RIDs are `win-x86`, `linux-x64`, `linux-arm64`, `osx-x64`,
and `osx-arm64`. The Windows x86 compiler also runs on Windows x64 and ARM64
through Windows compatibility support; it is not a native ARM64 binary.

Programmatic consumers should select a compatible host from
`toolset-manifest.json`, restore declared executable modes, resolve its binary
and required environment against the extracted root, and invoke that binary.
See the [consumer guide](docs/consumer-guide.md).

## Documentation

- [Consumer guide](docs/consumer-guide.md)
- [Build and release](docs/build-and-release.md)
- [Register an upstream release](docs/upstream-registration.md)
- [Source and build policy](docs/source-and-build.md)

Run tests with:

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
python -m unittest discover -s tests -v
```

Repository automation is MIT-licensed. The NSIS license is included at
`common/COPYING` in every toolset archive.
