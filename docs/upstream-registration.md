# Registering an upstream NSIS release

One configuration file is stored for each upstream NSIS version. For example:

    config/upstream/3.12.json

Local toolset labels such as r1, preview, and preview.2 do not create additional
upstream files. Both v3.12-r1 and v3.12-preview.2 use the same 3.12.json file.

Before running either script, copy SHA-1 and MD5 from the SourceForge file
information page. Obtain SOURCE_DATE_EPOCH from the official source archive's
UTC release time. These are explicit inputs so a checksum calculated from a
newly downloaded file is never misrepresented as an upstream-published
checksum.

Windows Command Prompt:

    scripts\register-upstream.cmd 3.12 1776631488 WINDOWS_SHA1 SOURCE_SHA1 WINDOWS_MD5 SOURCE_MD5

Linux or macOS system shell:

    sh scripts/register-upstream.sh 3.12 1776631488 WINDOWS_SHA1 SOURCE_SHA1 WINDOWS_MD5 SOURCE_MD5

The scripts download the official Windows and source archives, require their
published SHA-1 and MD5 to match, calculate SHA-256 and byte sizes locally, and
write config/upstream/<version>.json. Existing configuration is never
overwritten. Review and commit the generated file manually.

No Python, Node.js, PowerShell, or .NET runtime is used. Windows requires the
in-box curl.exe and certutil.exe. Linux/macOS require the usual system curl,
checksum utilities, and POSIX commands; the script supports both GNU sha*sum
and macOS shasum/md5.
