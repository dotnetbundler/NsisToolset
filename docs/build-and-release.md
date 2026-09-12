# Build and release

## Workflow

```text
resolve -> download -> common-and-windows-host-smoke -> native-hosts-smoke -> installer-smoke -> assemble -> release
```

| Job | Purpose |
| --- | --- |
| `resolve` | Validate the tag/input and select an upstream config |
| `download` | Download each upstream archive once and verify it |
| `common-and-windows-host-smoke` | Stage common files and the Windows x86 host, then run smoke compilation |
| `native-hosts-smoke` | Build four native hosts twice and run smoke compilation |
| `installer-smoke` | Install and uninstall all five smoke installers on Windows |
| `assemble` | Create records, verify the manifest, package twice, and test the relocated ZIP |
| `release` | Publish validated assets for a pushed version tag only |

Manual dispatch runs all validation but does not publish a Release.

## Generated directories

All build output is under `artifacts/`. Each CI job has its own filesystem, so
these paths do not all exist at the same time.

| Path | Purpose |
| --- | --- |
| `upstream/` | Verified upstream archives |
| `work/` | Extracted Windows archive |
| `stage/` | Toolset being assembled |
| `smoke/` | Smoke fixture and generated installer |
| `native-1/`, `native-2/` | Two native builds compared for reproducibility |
| `native-work/` | Native source and build directories |
| `installers/` | Smoke installers downloaded by `installer-smoke` |
| `installed/` | Temporary installation targets |
| `hosts/` | Native hosts downloaded by `assemble` |
| `repeat/` | Second ZIP used for byte comparison |
| `release package/` | Final ZIP extracted at a new path |
| `release package smoke/` | Final package smoke output |
| `dist/` | Files published with the GitHub Release |

Temporary Actions artifact names are `verified-upstream`, `windows-stage`,
`host-<rid>`, and `installer-<rid>`. Only `release-assets`, sourced from
`artifacts/dist/`, is passed to the release job.

## Local checks

The following example uses upstream NSIS 3.12 and toolset version `3.12-r1`.
Windows can validate the official host locally:

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
python -m build_tools.toolset_cli --upstream-config config/upstream/3.12.json --toolset-version 3.12-r1 download --cache artifacts/upstream
python -m build_tools.toolset_cli --upstream-config config/upstream/3.12.json --toolset-version 3.12-r1 stage-common --archive artifacts/upstream/nsis-3.12.zip --stage artifacts/stage --work artifacts/work
python -m build_tools.toolset_cli --upstream-config config/upstream/3.12.json --toolset-version 3.12-r1 stage-windows-host --archive artifacts/upstream/nsis-3.12.zip --stage artifacts/stage --work artifacts/work
python -m build_tools.ci_cli --upstream-config config/upstream/3.12.json --toolset-version 3.12-r1 windows-smoke --stage artifacts/stage --fixture fixtures/minimal.nsi --smoke artifacts/smoke
python -m build_tools.ci_cli test-installer --installer artifacts/smoke/smoke-installer.exe --install-root artifacts/installed/win-x86
python -m unittest discover -s tests -v
```

Linux and macOS production hosts must be built and validated by their native CI
runners.

## Versions

Tags use `v<upstream-version>-<local-label>`, for example `v3.12-r1` or
`v3.12-preview.2`. Local labels reuse the same upstream config and distinguish
the resulting archives and metadata.

To add another NSIS version, follow
[upstream-registration.md](upstream-registration.md).

## Publish a version

### 1. Prepare the version

Choose a tag such as `v3.12-r1`.

- For a new upstream NSIS version, register and commit its
  `config/upstream/<version>.json` first.
- For another local revision of an existing upstream version, reuse its config.
- Update the shared build documentation only when the build policy changes.

Confirm that the tag resolves correctly:

```powershell
$tag = 'v3.12-r1'
python -m build_tools.toolset_cli resolve-version --version $tag
```

### 2. Validate and push the commit

Run the local checks above. Commit all intended changes, make sure the working
tree is clean, and push the commit that will be released:

```powershell
git status --short
git push origin main
```

For a full pre-release check, manually run the `build-and-verify` workflow with
the same tag value, such as `v3.12-r1`. Manual dispatch builds and tests all
hosts but does not publish a Release. Wait for every job to pass.

### 3. Create and push the tag

Tag the exact commit that passed review and validation:

```powershell
git tag -a $tag -m "NSIS Toolset $tag"
git push origin $tag
```

Pushing the tag starts the workflow again. After all validation jobs pass, the
`release` job creates the GitHub Release.

### 4. Check the Release

Confirm that the Release tag and title are correct and that it contains:

```text
nsis-toolset-<version>.zip
nsis-toolset-<version>.zip.sha256
toolset-manifest.json
build-provenance.json
source-record.md
```

Download the ZIP and `.sha256` file and verify the checksum once. Do not replace
an existing published tag or its assets. Publish fixes with a new local label,
for example `v3.12-r2`.
