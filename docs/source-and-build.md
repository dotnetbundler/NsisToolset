# Source and build policy

Each upstream NSIS version has one machine-readable record at `config/upstream/<version>.json`. It contains the source date, official download URLs, sizes, and published and locally derived digests. No separate source record is generated for a Release.

## Source acceptance

A download is accepted only when its size, upstream-published SHA-1, and locally derived SHA-256 match the selected config. MD5 is retained as an upstream record but is not an acceptance check.

Register a new upstream version with [upstream-registration.md](upstream-registration.md).

## Build rules

- Native compilers use the official source without patches.
- Every host uses the shared `common/` directory through `NSISDIR`.
- Linux compilers are built in pinned manylinux2014 containers for a glibc 2.17 baseline. They dynamically link glibc and zlib, statically link the C++ runtime, and use the host system's matching iconv modules; imported GLIBC symbol versions and dynamic dependencies are checked during the build.
- macOS deployment targets are defined by the build configuration.
- Build dependencies are pinned in `requirements-build.txt`.
- Native compilers and the final ZIP are built twice and compared byte for byte.
- Every host reports the expected version and compiles both the repository's minimal installer and the official `Examples/bigtest.nsi`; Linux also compiles a Simplified Chinese language-file test. Every generated installer is installed, checked, and uninstalled before publication.

The Windows runtime comes from the verified official Windows ZIP.
