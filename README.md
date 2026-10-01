# NsisToolset

[简体中文](README.zh-CN.md)

NsisToolset packages NSIS as a portable toolset for Windows, Linux, and macOS. Download and extract it to use NSIS without installation.

## Use

Download `nsis-toolset-<version>.zip` from the matching [GitHub Release](https://github.com/dotnetbundler/NsisToolset/releases).

See [Release file structure](docs/release-file-structure.md) for the release assets and the directory layout inside the ZIP.

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

## System support

### Toolset

| System  | Host architectures                 | Version requirements                                                       |
| ------- | ---------------------------------- | -------------------------------------------------------------------------- |
| Windows | x86, x64, ARM64                    | [Windows 2000+](https://sourceforge.net/p/nsis/mailman/message/30230037/). |
| Linux   | x64, ARM64                         | glibc 2.17 or later.                                                       |
| macOS   | x64 (Intel), ARM64 (Apple Silicon) | macOS 10.13+.                                                              |

The minimum Windows version follows the compiler compatibility target stated by an upstream developer. For cross-architecture execution on Windows, see Microsoft's [WOW64 documentation](https://learn.microsoft.com/en-us/windows/win32/winprog64/running-32-bit-applications) and [Arm emulation documentation](https://learn.microsoft.com/en-us/windows/arm/apps-on-arm-x86-emulation).

Linux requires the `zlib` compression library (`libz.so.1`) and glibc's character encoding conversion modules, which read non-UTF-8 scripts and language files such as those encoded in CP936. Standard systems usually include these components; minimal systems may need to install them through the distribution's package manager.

### Generated installers

Generated installers run on Windows. The minimum versions below follow the [compatibility range in the official NSIS manual](https://nsis.sourceforge.io/Docs/Chapter1.html):

| Installer mode                    | Minimum system version                               |
| --------------------------------- | ---------------------------------------------------- |
| Unicode (`Unicode true`, default) | Windows NT 4.0+. Windows 95/98/ME are not supported. |
| ANSI (`Unicode false`)            | Windows 95+ or Windows NT 4.0+.                      |

NSIS [defaults to Unicode installers as of 3.07](https://nsis.sourceforge.io/Docs/AppendixF.html#v3.07). System features called by the script and plug-ins may raise the installer's minimum system requirements; the installed application's requirements must also be checked separately. These are upstream baseline compatibility ranges, not confirmation that this repository has tested every legacy Windows version. Test on the lowest target version before releasing.

## Release process

1. Register the config by following [Register an upstream release](docs/upstream-registration.md); skip this step if the release version already has a config.
2. (Optional) Run the local tests: `python -m unittest discover -s tests -v`
3. Push a tag in the `v<upstream-version>-<local-label>` format (for example, `v3.12-r1`), and the workflow will publish and test the Release automatically.

## License

Repository automation uses the [MIT License](LICENSE). The [NSIS license](https://nsis.sourceforge.io/Docs/AppendixI.html) is included as `common/COPYING`.
