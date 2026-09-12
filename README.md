# NsisToolset

[简体中文](README.zh-CN.md)

NsisToolset packages NSIS as a versioned, relocatable toolset for Windows,
Linux, and macOS build hosts. No system-wide NSIS installation is required.

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

The launcher selects the correct host compiler and configures `NSISDIR`.
See the [consumer guide](docs/consumer-guide.md) for checksum commands.

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
