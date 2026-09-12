# Consumer guide

Download these two files from the same GitHub Release:

- `nsis-toolset-<version>.zip`
- `nsis-toolset-<version>.zip.sha256`

Verify the ZIP, extract it, and run the launcher in its root directory:

```powershell
$checksum = Get-ChildItem 'nsis-toolset-*.zip.sha256' | Select-Object -First 1
$zip = $checksum.FullName -replace '\.sha256$', ''
$expected = (Get-Content $checksum.FullName).Split()[0]
$actual = (Get-FileHash $zip -Algorithm SHA256).Hash
if ($actual -ne $expected) { throw 'checksum mismatch' }

Expand-Archive $zip -DestinationPath nsis-toolset
.\nsis-toolset\makensis.cmd path\to\installer.nsi
```

```sh
sha256sum --check nsis-toolset-*.zip.sha256
unzip nsis-toolset-*.zip -d nsis-toolset
./nsis-toolset/makensis path/to/installer.nsi
```

The launcher selects the correct host compiler and configures `NSISDIR`.
Nothing else needs to be installed or configured.

The ZIP contains only the two launchers, shared NSIS files under `common/`, and
host compilers under `hosts/`. The Windows x86 compiler also runs on Windows
x64 and ARM64 through Windows compatibility support.
