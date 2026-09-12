# Build and release

The workflow downloads hash-pinned upstream files, builds and smoke-tests every
host, assembles the toolset twice to check reproducibility, and tests the final
ZIP after extraction. Manual runs validate without publishing. A matching
version tag publishes only after the same checks pass.

Run the unit tests locally with `python -m unittest discover -s tests -v`.
Use a manual workflow run when all native hosts need to be validated before
publishing.

## Versions

Tags use `v<upstream-version>-<local-label>`. A new upstream version needs one
new config under `config/upstream/`; another toolset revision reuses that config.
See [upstream-registration.md](upstream-registration.md).

## Publish a version

Commit and push the intended changes. You may run the workflow manually first
for a full check. Then tag that commit and push the tag:

```powershell
$tag = 'v<upstream-version>-<local-label>'
git status --short
git push origin main
git tag -a $tag -m "NSIS Toolset $tag"
git push origin $tag
```

The workflow creates the Release after all checks pass. It contains only:

- `nsis-toolset-<version>.zip`
- `nsis-toolset-<version>.zip.sha256`

Do not replace a published tag. Publish a fix with a new local label.
