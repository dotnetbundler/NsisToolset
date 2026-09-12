# Consumer guide

Use assets from a versioned GitHub Release. Actions artifacts are temporary CI
files and must not be used as release dependencies.

## Release assets

| Asset | Content |
| --- | --- |
| `nsis-toolset-<version>.zip` | Complete toolset |
| `nsis-toolset-<version>.zip.sha256` | ZIP checksum |
| `toolset-manifest.json` | File and host metadata |
| `build-provenance.json` | Build environment and native-host records |
| `source-record.md` | Upstream URLs and checksums |

## Verify

Verify the ZIP before extracting it. The following commands use `3.12-r1` as
an example:

```sh
sha256sum --check nsis-toolset-3.12-r1.zip.sha256
```

```powershell
$expected = (Get-Content nsis-toolset-3.12-r1.zip.sha256).Split()[0]
$actual = (Get-FileHash nsis-toolset-3.12-r1.zip -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actual -ne $expected) { throw 'checksum mismatch' }
```

After extraction, verify the `size` and `sha256` of every file listed in
`toolset-manifest.json`. Restore `unixMode` for files whose
`requiresExecutable` value is `true`.

## Layout

```text
makensis
makensis.cmd
common/
hosts/
  win-x86/      makensis.exe zlib1.dll
  linux-x64/    makensis
  linux-arm64/  makensis
  osx-x64/      makensis
  osx-arm64/    makensis
build-record.json
SOURCE-RECORD.md
toolset-manifest.json
```

`common/` contains NSIS headers, plug-ins, stubs, contributed files, config,
and license data shared by every host.

## Invoke

Humans can use the root `makensis.cmd` or `makensis` launcher. The launcher sets
`NSISDIR` and selects the current host.

Programs should:

1. Read `toolset-manifest.json`.
2. Select a host whose `compatibleHostRids` contains the current RID.
3. Resolve its `binary` against the toolset root.
4. Resolve its `requiredEnvironment` values against the same root.
5. Restore required executable modes and run the binary.

Pin the outer ZIP SHA-256 in downstream dependency metadata. Verifying only the
inner manifest does not identify which ZIP was downloaded.
