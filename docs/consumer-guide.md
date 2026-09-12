# Consuming an NsisToolset release

Use a versioned GitHub Release. GitHub Actions artifacts are temporary pipeline
transport and are not release channels. Do not consume an Actions artifact or a
`latest` URL as a production dependency.

## Release assets

A release contains:

| Asset | Purpose |
| --- | --- |
| `nsis-toolset-<version>.zip` | Complete relocatable toolset |
| `nsis-toolset-<version>.zip.sha256` | SHA-256 of the complete ZIP |
| `toolset-manifest.json` | A copy of the manifest stored inside the ZIP |
| `build-provenance.json` | CI runner, toolchain, source commit, and native-host build facts |
| `source-record.md` | Upstream URLs, sizes, and recorded digests for this build |

The ZIP contains `SOURCE-RECORD.md` with uppercase naming. The separately
uploaded Release asset uses lowercase `source-record.md`; their source data is
the same.

## Verify and extract

First verify the downloaded ZIP against its adjacent checksum file. On Linux or
macOS:

```sh
sha256sum --check nsis-toolset-3.12-r1.zip.sha256
```

On Windows PowerShell:

```powershell
$expected = (Get-Content nsis-toolset-3.12-r1.zip.sha256).Split()[0]
$actual = (Get-FileHash nsis-toolset-3.12-r1.zip -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actual -ne $expected) { throw 'NSIS toolset checksum mismatch' }
```

After extraction, verify every file listed in `toolset-manifest.json` against
its `size` and `sha256`. Reject missing, modified, and undeclared files.

ZIP extractors do not consistently restore Unix executable modes. Apply each
file's `unixMode` when `requiresExecutable` is `true` before executing it.

## Toolset layout

```text
makensis
makensis.cmd
common/
  Include/ Plugins/ Stubs/ Contrib/
  nsisconf.nsh COPYING
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

`common/` comes from the matching official Windows ZIP and is not duplicated
per host. `Plugins` is target data used while producing Windows installers; it
is not a dynamic dependency of the current build host.

The official Windows runtime is `Bin/makensis.exe` plus `Bin/zlib1.dll` from
the upstream ZIP. The small upstream root `makensis.exe` is a launcher and is
not shipped as a host compiler.

## Invocation contracts

For interactive use, run `makensis.cmd` at the toolset root on Windows or
`makensis` at the root on Linux and macOS. The POSIX launcher selects a native
host from `uname`; unsupported systems or architectures fail explicitly.

Programmatic consumers should not duplicate that dispatch logic. Instead:

1. Read `toolset-manifest.json`.
2. Select one host whose `compatibleHostRids` contains the current runtime ID.
3. Resolve the host's `binary` path against the extracted toolset root.
4. Resolve every `requiredEnvironment` entry against the same root. Each current
   host requires `NSISDIR` to point to `common`.
5. Restore executable modes declared by the manifest.
6. Invoke the selected binary with the resolved environment.

The Windows compiler is PE x86. Its compatibility list includes Windows x64
and Windows ARM64, but ARM64 executes it through Windows x86 compatibility; the
toolset does not claim a native Windows ARM64 compiler.

## Integrity model

Every packaged file has a SHA-256, byte size, normalized Unix mode, and
executable requirement in the manifest. Host records additionally describe the
real binary, runtime files, architecture, compatible runtime IDs, required
environment, and minimum-OS statement.

Pin the versioned outer ZIP digest in downstream dependency metadata. Verifying
only the inner manifest without pinning the outer asset does not authenticate
which manifest was downloaded.
