# NsisToolset

[简体中文](README.zh-CN.md)

NsisToolset packages NSIS as a portable toolset for Windows, Linux, and macOS. Download and extract it to use NSIS without installation.

## Use

Download `nsis-toolset-<version>.zip` from the matching [GitHub Release](https://github.com/dotnetbundler/NsisToolset/releases).

### Verification (optional)

Download the `.sha256` file to verify the ZIP.

Windows:

```powershell
$version = '<version>'
$expected = (Get-Content "nsis-toolset-$version.zip.sha256").Split()[0]
$actual = (Get-FileHash "nsis-toolset-$version.zip" -Algorithm SHA256).Hash
if ($actual -ne $expected) { throw 'checksum mismatch' }
```

Linux:

```sh
sha256sum --check nsis-toolset-<version>.zip.sha256
```

macOS:

```sh
shasum -a 256 --check nsis-toolset-<version>.zip.sha256
```

### Run

Windows:

```powershell
.\makensis.cmd path\to\installer.nsi
```

Linux or macOS:

```sh
./makensis path/to/installer.nsi
```

The launcher automatically selects the compiler for the current host and configures `NSISDIR`.

### FAQ

#### Permission denied on Linux or macOS

If the extraction tool did not preserve executable permissions, run:

```sh
chmod +x makensis hosts/*/makensis
```

#### Linux compatibility

The Linux hosts require glibc 2.17 or later. Alpine Linux and other musl-based systems are not supported.

## Release process

1. Register the config by following [Register an upstream release](docs/upstream-registration.md); skip this step if the release version already has a config.
2. (Optional) Run the local tests: `python -m unittest discover -s tests -v`
3. Push a tag in the `v<upstream-version>-<local-label>` format (for example, `v3.12-r1`), and the workflow will publish the Release automatically.

## License

Repository automation uses the [MIT License](LICENSE). The [NSIS license](https://nsis.sourceforge.io/Docs/AppendixI.html) is included as `common/COPYING`.
