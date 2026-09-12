@echo off
setlocal EnableExtensions EnableDelayedExpansion

if "%~6"=="" goto :usage
if not "%~9"=="" goto :usage

set "VERSION=%~1"
set "SOURCE_DATE_UTC=%~2"
set "WINDOWS_SHA1=%~3"
set "WINDOWS_MD5=%~4"
set "SOURCE_SHA1=%~5"
set "SOURCE_MD5=%~6"
set "KEEP_DOWNLOADS=0"
if not "%~7"=="" (
  if /i not "%~7"=="--keep-downloads" goto :usage
  set "KEEP_DOWNLOADS=1"
)

echo [1/7] Validating arguments and required system commands
where curl.exe >nul 2>nul || (echo required system command not found: curl.exe>&2 & exit /b 1)
where certutil.exe >nul 2>nul || (echo required system command not found: certutil.exe>&2 & exit /b 1)
where powershell.exe >nul 2>nul || (echo required system command not found: powershell.exe>&2 & exit /b 1)
echo(%VERSION%| findstr /r /x "[0-9][0-9.]*" >nul || (echo invalid NSIS version>&2 & exit /b 2)
echo(%VERSION%| findstr "\." >nul || (echo NSIS version must contain a dot>&2 & exit /b 2)
if "%VERSION:~0,1%"=="." (echo invalid NSIS version>&2 & exit /b 2)
if "%VERSION:~-1%"=="." (echo invalid NSIS version>&2 & exit /b 2)
if not "%VERSION:..=%"=="%VERSION%" (echo invalid NSIS version>&2 & exit /b 2)
set "EPOCH="
for /f "usebackq delims=" %%I in (`powershell.exe -NoProfile -NonInteractive -Command "try { [DateTimeOffset]::ParseExact($env:SOURCE_DATE_UTC, 'yyyy-MM-dd HH:mm:ss ''UTC''', [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::AssumeUniversal).ToUnixTimeSeconds() } catch { exit 1 }"`) do set "EPOCH=%%I"
if not defined EPOCH (echo source-date-epoch must be a valid UTC date with format YYYY-MM-DD HH:MM:SS UTC>&2 & exit /b 2)
echo(%WINDOWS_SHA1%| findstr /r /i /x "[0-9a-f][0-9a-f]*" >nul || (echo invalid Windows SHA-1>&2 & exit /b 2)
echo(%SOURCE_SHA1%| findstr /r /i /x "[0-9a-f][0-9a-f]*" >nul || (echo invalid source SHA-1>&2 & exit /b 2)
echo(%WINDOWS_MD5%| findstr /r /i /x "[0-9a-f][0-9a-f]*" >nul || (echo invalid Windows MD5>&2 & exit /b 2)
echo(%SOURCE_MD5%| findstr /r /i /x "[0-9a-f][0-9a-f]*" >nul || (echo invalid source MD5>&2 & exit /b 2)
if not "%WINDOWS_SHA1:~40,1%"=="" (echo Windows SHA-1 is too long>&2 & exit /b 2)
if "%WINDOWS_SHA1:~39,1%"=="" (echo Windows SHA-1 is too short>&2 & exit /b 2)
if not "%SOURCE_SHA1:~40,1%"=="" (echo source SHA-1 is too long>&2 & exit /b 2)
if "%SOURCE_SHA1:~39,1%"=="" (echo source SHA-1 is too short>&2 & exit /b 2)
if not "%WINDOWS_MD5:~32,1%"=="" (echo Windows MD5 is too long>&2 & exit /b 2)
if "%WINDOWS_MD5:~31,1%"=="" (echo Windows MD5 is too short>&2 & exit /b 2)
if not "%SOURCE_MD5:~32,1%"=="" (echo source MD5 is too long>&2 & exit /b 2)
if "%SOURCE_MD5:~31,1%"=="" (echo source MD5 is too short>&2 & exit /b 2)

for %%I in ("%~dp0..") do set "REPO_ROOT=%%~fI"
set "OUTPUT=%REPO_ROOT%\config\upstream\%VERSION%.json"
if exist "%OUTPUT%" (echo refusing to overwrite existing config: %OUTPUT%>&2 & exit /b 1)

echo [2/7] Preparing the download directory
if "%KEEP_DOWNLOADS%"=="0" (
  set "WORK=%TEMP%\nsis-upstream-%RANDOM%-%RANDOM%"
  set "CLEANUP=1"
) else (
  if "%~8"=="" (
    set "WORK=%REPO_ROOT%\.cache\upstream\%VERSION%"
  ) else (
    for %%I in ("%~8") do set "WORK=%%~fI"
  )
  set "CLEANUP=0"
)
mkdir "%WORK%" 2>nul
if not exist "%WORK%" (echo failed to create download directory: %WORK%>&2 & exit /b 1)
echo Download directory: %WORK%

set "WINDOWS_NAME=nsis-%VERSION%.zip"
set "SOURCE_NAME=nsis-%VERSION%-src.tar.bz2"
set "BASE_URL=https://sourceforge.net/projects/nsis/files/NSIS%%203/%VERSION%"
set "WINDOWS_URL=%BASE_URL%/%WINDOWS_NAME%/download"
set "SOURCE_URL=%BASE_URL%/%SOURCE_NAME%/download"
set "WINDOWS_FILE=%WORK%\%WINDOWS_NAME%"
set "SOURCE_FILE=%WORK%\%SOURCE_NAME%"

echo [3/7] Downloading the Windows archive
curl.exe -fL --retry 2 --output "%WINDOWS_FILE%" "%WINDOWS_URL%" || goto :download_error
echo [4/7] Downloading the source archive
curl.exe -fL --retry 2 --output "%SOURCE_FILE%" "%SOURCE_URL%" || goto :download_error

echo [5/7] Verifying the published SHA-1 and MD5 values
call :hash "%WINDOWS_FILE%" SHA1 ACTUAL_WINDOWS_SHA1 || goto :hash_error
call :hash "%SOURCE_FILE%" SHA1 ACTUAL_SOURCE_SHA1 || goto :hash_error
if /i not "%ACTUAL_WINDOWS_SHA1%"=="%WINDOWS_SHA1%" (echo Windows archive does not match the upstream-published SHA-1>&2 & goto :failure)
if /i not "%ACTUAL_SOURCE_SHA1%"=="%SOURCE_SHA1%" (echo source archive does not match the upstream-published SHA-1>&2 & goto :failure)
call :hash "%WINDOWS_FILE%" MD5 ACTUAL_WINDOWS_MD5 || goto :hash_error
call :hash "%SOURCE_FILE%" MD5 ACTUAL_SOURCE_MD5 || goto :hash_error
if /i not "%ACTUAL_WINDOWS_MD5%"=="%WINDOWS_MD5%" (echo Windows archive MD5 differs from the published record>&2 & goto :failure)
if /i not "%ACTUAL_SOURCE_MD5%"=="%SOURCE_MD5%" (echo source archive MD5 differs from the published record>&2 & goto :failure)
echo Published checksums match.
echo [6/7] Calculating SHA-256 values and archive sizes
call :hash "%WINDOWS_FILE%" SHA256 WINDOWS_SHA256 || goto :hash_error
call :hash "%SOURCE_FILE%" SHA256 SOURCE_SHA256 || goto :hash_error
for %%I in ("%WINDOWS_FILE%") do set "WINDOWS_SIZE=%%~zI"
for %%I in ("%SOURCE_FILE%") do set "SOURCE_SIZE=%%~zI"
if not exist "%REPO_ROOT%\config\upstream" mkdir "%REPO_ROOT%\config\upstream"

echo [7/7] Writing the upstream configuration
(
echo {
echo   "schemaVersion": 1,
echo   "upstreamVersion": "%VERSION%",
echo   "sourceDateEpoch": %EPOCH%,
echo   "upstream": {
echo     "windowsZip": {
echo       "fileName": "%WINDOWS_NAME%",
echo       "url": "%WINDOWS_URL%",
echo       "size": %WINDOWS_SIZE%,
echo       "digests": {
echo         "upstreamPublished": {
echo           "sha1": "%ACTUAL_WINDOWS_SHA1%",
echo           "md5": "%WINDOWS_MD5%"
echo         },
echo         "locallyDerived": {
echo           "sha256": "%WINDOWS_SHA256%"
echo         }
echo       }
echo     },
echo     "sourceArchive": {
echo       "fileName": "%SOURCE_NAME%",
echo       "url": "%SOURCE_URL%",
echo       "size": %SOURCE_SIZE%,
echo       "digests": {
echo         "upstreamPublished": {
echo           "sha1": "%ACTUAL_SOURCE_SHA1%",
echo           "md5": "%SOURCE_MD5%"
echo         },
echo         "locallyDerived": {
echo           "sha256": "%SOURCE_SHA256%"
echo         }
echo       }
echo     }
echo   }
echo }
)>"%OUTPUT%"

echo wrote %OUTPUT%
echo review the new file before committing it
call :cleanup
if "%CLEANUP%"=="1" (
  echo Downloaded files deleted ^(default^).
) else (
  echo Downloaded files retained at: %WORK%
)
exit /b 0

:hash
set "HASH_LINE="
set "HASH_LAST_INDEX=39"
set "HASH_LENGTH=40"
if /i "%~2"=="MD5" (
  set "HASH_LAST_INDEX=31"
  set "HASH_LENGTH=32"
)
if /i "%~2"=="SHA256" (
  set "HASH_LAST_INDEX=63"
  set "HASH_LENGTH=64"
)
for /f "tokens=* delims=" %%H in ('certutil.exe -hashfile "%~1" %~2') do (
  set "CANDIDATE=%%H"
  set "CANDIDATE=!CANDIDATE: =!"
  set "NON_HEX="
  for /f "delims=0123456789abcdefABCDEF" %%X in ("!CANDIDATE!") do set "NON_HEX=%%X"
  if not defined NON_HEX if defined CANDIDATE if not "!CANDIDATE:~%HASH_LAST_INDEX%,1!"=="" if "!CANDIDATE:~%HASH_LENGTH%,1!"=="" if not defined HASH_LINE set "HASH_LINE=!CANDIDATE!"
)
if not defined HASH_LINE exit /b 1
set "%~3=!HASH_LINE!"
exit /b 0

:download_error
echo download failed>&2
goto :failure
:hash_error
echo hash calculation failed>&2
:failure
call :cleanup
exit /b 1

:cleanup
if "%CLEANUP%"=="1" if defined WORK if exist "%WORK%" (
  echo Removing downloaded files: %WORK%
  rmdir /s /q "%WORK%"
)
exit /b 0

:usage
echo usage: %~nx0 ^<version^> ^<source-date-epoch^> ^<windows-sha1^> ^<windows-md5^> ^<source-sha1^> ^<source-md5^> [--keep-downloads [directory]]>&2
exit /b 2
