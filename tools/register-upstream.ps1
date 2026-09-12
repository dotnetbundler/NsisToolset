#Requires -Version 5.1

#Requires -Version 5.1

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string] $Version,

    [Parameter(Mandatory = $true, Position = 1)]
    [string] $SourceDateEpoch,

    [Parameter(Mandatory = $true, Position = 2)]
    [string] $WindowsSha1,

    [Parameter(Mandatory = $true, Position = 3)]
    [string] $WindowsMd5,

    [Parameter(Mandatory = $true, Position = 4)]
    [string] $SourceSha1,

    [Parameter(Mandatory = $true, Position = 5)]
    [string] $SourceMd5,

    [switch] $KeepDownloads,

    [string] $DownloadDirectory
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
trap {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}

function Assert-Matches {
    param(
        [string] $Value,
        [string] $Pattern,
        [string] $Message
    )

    if ($Value -cnotmatch $Pattern) {
        throw $Message
    }
}

function Get-LowerHash {
    param(
        [string] $Path,
        [string] $Algorithm
    )

    return (Get-FileHash -LiteralPath $Path -Algorithm $Algorithm).Hash.ToLowerInvariant()
}

function Invoke-Download {
    param(
        [string] $Uri,
        [string] $OutFile
    )

    & curl.exe -fL --retry 2 --output $OutFile $Uri
    if ($LASTEXITCODE -ne 0) {
        throw "download failed with exit code $LASTEXITCODE"
    }
}

Write-Host '[1/7] Validating arguments'
if (-not (Get-Command curl.exe -ErrorAction SilentlyContinue)) {
    throw 'required system command not found: curl.exe'
}
Assert-Matches $Version '^[0-9]+(\.[0-9]+){1,3}$' 'version must be a numeric NSIS version such as 3.12 or 3.06.1'
Assert-Matches $SourceDateEpoch '^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2} UTC$' 'source-date-epoch must have format YYYY-MM-DD HH:MM:SS UTC'
Assert-Matches $WindowsSha1 '^[0-9a-fA-F]{40}$' 'Windows SHA-1 must contain exactly 40 hexadecimal characters'
Assert-Matches $WindowsMd5 '^[0-9a-fA-F]{32}$' 'Windows MD5 must contain exactly 32 hexadecimal characters'
Assert-Matches $SourceSha1 '^[0-9a-fA-F]{40}$' 'source SHA-1 must contain exactly 40 hexadecimal characters'
Assert-Matches $SourceMd5 '^[0-9a-fA-F]{32}$' 'source MD5 must contain exactly 32 hexadecimal characters'
if ($DownloadDirectory -and -not $KeepDownloads) {
    throw '-DownloadDirectory requires -KeepDownloads'
}

try {
    $sourceDate = [DateTimeOffset]::ParseExact(
        $SourceDateEpoch,
        "yyyy-MM-dd HH:mm:ss 'UTC'",
        [Globalization.CultureInfo]::InvariantCulture,
        [Globalization.DateTimeStyles]::AssumeUniversal
    )
}
catch {
    throw 'source-date-epoch is not a valid UTC date'
}
$epoch = $sourceDate.ToUnixTimeSeconds()

$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$output = Join-Path $repoRoot "config\upstream\$Version.json"
if (Test-Path -LiteralPath $output) {
    throw "refusing to overwrite existing config: $output"
}

$cleanup = -not $KeepDownloads
if ($KeepDownloads) {
    if ($DownloadDirectory) {
        $work = [IO.Path]::GetFullPath($DownloadDirectory)
    }
    else {
        $work = Join-Path $repoRoot ".cache\upstream\$Version"
    }
}
else {
    $work = Join-Path ([IO.Path]::GetTempPath()) ("nsis-upstream-" + [Guid]::NewGuid().ToString('N'))
}

Write-Host '[2/7] Preparing the download directory'
[void] (New-Item -ItemType Directory -Force -Path $work)
Write-Host "Download directory: $work"

$windowsName = "nsis-$Version.zip"
$sourceName = "nsis-$Version-src.tar.bz2"
$baseUrl = "https://sourceforge.net/projects/nsis/files/NSIS%203/$Version"
$windowsUrl = "$baseUrl/$windowsName/download"
$sourceUrl = "$baseUrl/$sourceName/download"
$windowsFile = Join-Path $work $windowsName
$sourceFile = Join-Path $work $sourceName

try {
    Write-Host '[3/7] Downloading the Windows archive'
    Invoke-Download $windowsUrl $windowsFile
    Write-Host '[4/7] Downloading the source archive'
    Invoke-Download $sourceUrl $sourceFile

    Write-Host '[5/7] Verifying the published SHA-1 and MD5 values'
    $actualWindowsSha1 = Get-LowerHash $windowsFile 'SHA1'
    $actualSourceSha1 = Get-LowerHash $sourceFile 'SHA1'
    $actualWindowsMd5 = Get-LowerHash $windowsFile 'MD5'
    $actualSourceMd5 = Get-LowerHash $sourceFile 'MD5'
    if ($actualWindowsSha1 -ne $WindowsSha1.ToLowerInvariant()) { throw 'Windows archive does not match the upstream-published SHA-1' }
    if ($actualSourceSha1 -ne $SourceSha1.ToLowerInvariant()) { throw 'source archive does not match the upstream-published SHA-1' }
    if ($actualWindowsMd5 -ne $WindowsMd5.ToLowerInvariant()) { throw 'Windows archive MD5 differs from the published record' }
    if ($actualSourceMd5 -ne $SourceMd5.ToLowerInvariant()) { throw 'source archive MD5 differs from the published record' }
    Write-Host 'Published checksums match.'

    Write-Host '[6/7] Calculating SHA-256 values and archive sizes'
    $windowsSha256 = Get-LowerHash $windowsFile 'SHA256'
    $sourceSha256 = Get-LowerHash $sourceFile 'SHA256'
    $windowsSize = (Get-Item -LiteralPath $windowsFile).Length
    $sourceSize = (Get-Item -LiteralPath $sourceFile).Length

    Write-Host '[7/7] Writing the upstream configuration'
    $json = @"
{
  "schemaVersion": 1,
  "upstreamVersion": "$Version",
  "sourceDateEpoch": $epoch,
  "upstream": {
    "windowsZip": {
      "fileName": "$windowsName",
      "url": "$windowsUrl",
      "size": $windowsSize,
      "digests": {
        "upstreamPublished": {
          "sha1": "$actualWindowsSha1",
          "md5": "$actualWindowsMd5"
        },
        "locallyDerived": {
          "sha256": "$windowsSha256"
        }
      }
    },
    "sourceArchive": {
      "fileName": "$sourceName",
      "url": "$sourceUrl",
      "size": $sourceSize,
      "digests": {
        "upstreamPublished": {
          "sha1": "$actualSourceSha1",
          "md5": "$actualSourceMd5"
        },
        "locallyDerived": {
          "sha256": "$sourceSha256"
        }
      }
    }
  }
}
"@
    $utf8WithoutBom = New-Object System.Text.UTF8Encoding($false)
    [IO.File]::WriteAllText($output, (($json -replace "`r`n", "`n") + "`n"), $utf8WithoutBom)
    Write-Host "wrote $output"
    Write-Host 'review the new file before committing it'
}
finally {
    if ($cleanup -and (Test-Path -LiteralPath $work)) {
        $resolvedWork = [IO.Path]::GetFullPath($work)
        $tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
        if (-not $resolvedWork.StartsWith($tempRoot, [StringComparison]::OrdinalIgnoreCase)) {
            throw "refusing to remove temporary directory outside the system temp directory: $resolvedWork"
        }
        Write-Host "Removing downloaded files: $resolvedWork"
        Remove-Item -LiteralPath $resolvedWork -Recurse -Force
    }
}

if ($cleanup) {
    Write-Host 'Downloaded files deleted (default).'
}
else {
    Write-Host "Downloaded files retained at: $work"
}
