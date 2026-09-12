# Building and releasing NsisToolset

This document is for repository maintainers. Consumers should use the
[consumer guide](consumer-guide.md).

## Workflow

The pipeline is intentionally ordered as follows:

```text
resolve -> download -> windows-host -> native-hosts -> install-test -> assemble -> release
```

1. `resolve` validates the pushed tag or manual input, selects the longest
   matching registered upstream version, and exports version, archive, config,
   and `SOURCE_DATE_EPOCH` values.
2. `download` downloads the official Windows ZIP and source archive once and
   verifies byte size, upstream-published SHA-1, and locally recorded SHA-256.
3. `windows-host` stages common data and root launchers, stages the official
   Windows x86 runtime separately, and compiles the smoke fixture through the
   root `makensis.cmd` launcher.
4. `native-hosts` builds `linux-x64`, `linux-arm64`, `osx-x64`, and `osx-arm64`
   on native GitHub-hosted runners. Each matrix entry builds twice, compares the
   compiler bytes, adds its host to the downloaded Windows stage, and compiles
   the fixture through the root POSIX launcher.
5. `install-test` downloads all five smoke installers on Windows. It silently
   installs, checks the marker, silently uninstalls, and requires no remaining
   installation directory for each host-generated installer.
6. `assemble` downloads the Windows stage and four native hosts on Ubuntu, runs
   unit tests, writes release records and provenance, packages twice, compares
   ZIP bytes, and validates the final package after extraction to a different
   path containing spaces.
7. `release` runs only for a pushed valid version tag. It rechecks the Git tag
   against the resolved toolset version and publishes the already validated
   release assets. A manual dispatch stops after validation.

Native compiler reproducibility means two builds on the same runner, with the
same verified source archive, environment, and arguments, must produce
byte-identical `makensis` binaries. It does not claim identical binaries across
different operating systems, architectures, or toolchain versions.

## Generated directories

All repository build output is placed under `artifacts/`, which is ignored by
Git. GitHub Actions jobs have isolated filesystems, so the following directories
do not all coexist in one job.

| Path | Contents and lifetime |
| --- | --- |
| `artifacts/upstream/` | Verified Windows and source archives |
| `artifacts/work/official-windows/` | Temporary extraction of the Windows ZIP |
| `artifacts/stage/` | Common data, root launchers, and staged hosts awaiting packaging |
| `artifacts/smoke/` | Fixture copy and the current host's `smoke-installer.exe` |
| `artifacts/native-1/` | First native compiler build and its metadata/reports |
| `artifacts/native-2/` | Second native compiler build used for byte comparison |
| `artifacts/native-work/<rid>-1/` | First native source/build/install work tree |
| `artifacts/native-work/<rid>-2/` | Second native source/build/install work tree |
| `artifacts/installers/` | Five downloaded smoke-installer artifacts |
| `artifacts/installed/<rid>/` | Temporary install-test target; removed by successful uninstall |
| `artifacts/hosts/host-<rid>/` | Native host artifacts downloaded by `assemble` |
| `artifacts/build-provenance.json` | External build provenance before copying to `dist` |
| `artifacts/dist/` | Final publishable assets |
| `artifacts/repeat/` | Second package output used only for reproducibility comparison |
| `artifacts/release package/` | Final ZIP extracted for relocation validation |
| `artifacts/release package smoke/` | Smoke compilation performed with the relocated package |

The Actions artifact names map to local paths as follows:

| Actions artifact | Uploaded path |
| --- | --- |
| `verified-upstream` | `artifacts/upstream/` |
| `windows-stage` | `artifacts/stage/` |
| `host-<rid>` | `artifacts/native-1/` |
| `installer-<rid>` | `artifacts/smoke/smoke-installer.exe` |
| `release-assets` | `artifacts/dist/` |

Actions artifacts are only job-to-job transport. They are not supported
distribution assets.

## Python responsibilities

| Module | Responsibility |
| --- | --- |
| `build_tools/configuration.py` | Version resolution and configuration merging |
| `build_tools/upstream.py` | Download, digest verification, and safe extraction |
| `build_tools/staging.py` | Common data, launcher, and host staging |
| `build_tools/native_build.py` | Native source builds and binary/toolchain audits |
| `build_tools/packaging.py` | Build/source records, manifest, verification, and deterministic ZIPs |
| `build_tools/smoke_tests.py` | Root-launcher smoke tests and final-package relocation test |
| `build_tools/release_tasks.py` | Assembly, provenance, installer tests, and publishing |
| `build_tools/toolset_cli.py` | Reusable local and CI operations |
| `build_tools/ci_cli.py` | CI-specific orchestration commands |
| `build_tools/ci_support.py` | Shared process and filesystem helpers |

The Python code is production automation, not toolset content. Packaging rejects
repository implementation directories such as `build_tools/`, `tests/`,
`.github/`, `config/`, and `fixtures/` if they leak into the staged release.

## Local validation

Windows can validate the official compiler and root launcher locally:

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
python -m build_tools.toolset_cli --upstream-config config/upstream/3.12.json --toolset-version 3.12-r1 download --cache artifacts/upstream
python -m build_tools.toolset_cli --upstream-config config/upstream/3.12.json --toolset-version 3.12-r1 stage-common --archive artifacts/upstream/nsis-3.12.zip --stage artifacts/stage --work artifacts/work
python -m build_tools.toolset_cli --upstream-config config/upstream/3.12.json --toolset-version 3.12-r1 stage-windows-host --archive artifacts/upstream/nsis-3.12.zip --stage artifacts/stage --work artifacts/work
python -m build_tools.ci_cli --upstream-config config/upstream/3.12.json --toolset-version 3.12-r1 windows-smoke --stage artifacts/stage --fixture fixtures/minimal.nsi --smoke artifacts/smoke
python -m build_tools.ci_cli test-installer --installer artifacts/smoke/smoke-installer.exe --install-root artifacts/installed/win-x86
python -m unittest discover -s tests -v
```

Linux and macOS production binaries must be built and audited on their native
CI runners. A local Windows run cannot validate those outputs.

## Versions and publication

One file under `config/upstream/` describes each upstream NSIS version. Local
labels such as `r1`, `r2`, or `preview.2` reuse that upstream configuration but
remain part of the manifest, archive name, build record, and Release metadata.

To register another upstream release, follow
[upstream-registration.md](upstream-registration.md). Review the resulting
configuration, upstream layout and runtime dependencies, source build flags,
licenses, native matrix, reproducibility checks, relocation check, and all-host
installer tests before pushing the version tag.
