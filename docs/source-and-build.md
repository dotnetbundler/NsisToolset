# Source and build policy

Each upstream NSIS version has one machine-readable record at
`config/upstream/<version>.json`. It contains the source date, official download
URLs, sizes, and published and locally derived digests. No separate source
record is generated for a Release.

## Source acceptance

A download is accepted only when its size, upstream-published SHA-1, and locally
derived SHA-256 match the selected config. MD5 is retained as an upstream record
but is not an acceptance check.

Register a new upstream version with
[upstream-registration.md](upstream-registration.md). This policy document only
changes when the policy changes; it is not copied for each version.

## Build rules

- Native compilers use the official source without patches.
- Every host uses the shared `common/` directory through `NSISDIR`.
- Linux compilers are static and their GNU ABI notes are checked.
- macOS deployment targets are defined by the build configuration.
- Build dependencies are pinned in `requirements-build.txt`.
- Native compilers and the final ZIP are built twice and compared byte for byte.
- Every host and generated installer passes smoke tests before publication.

The Windows runtime comes from the verified official Windows ZIP. The toolset
ZIP includes the NSIS license at `common/COPYING`; repository automation is
covered by the root `LICENSE`.
