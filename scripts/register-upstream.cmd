@echo off
setlocal EnableExtensions EnableDelayedExpansion

if "%~6"=="" goto :usage
if not "%~8"=="" goto :usage

set "VERSION=%~1"
set "EPOCH=%~2"
set "WINDOWS_SHA1=%~3"
set "SOURCE_SHA1=%~4"
set "WINDOWS_MD5=%~5"
set "SOURCE_MD5=%~6"

where curl.exe >nul 2>nul || (echo required system command not found: curl.exe>&2 & exit /b 1)
where certutil.exe >nul 2>nul || (echo required system command not found: certutil.exe>&2 & exit /b 1)
echo(%VERSION%| findstr /r /x "[0-9][0-9.]*" >nul || (echo invalid NSIS version>&2 & exit /b 2)
echo(%VERSION%| findstr "\." >nul || (echo NSIS version must contain a dot>&2 & exit /b 2)
if "%VERSION:~0,1%"=="." (echo invalid NSIS version>&2 & exit /b 2)
if "%VERSION:~-1%"=="." (echo invalid NSIS version>&2 & exit /b 2)
if not "%VERSION:..=%"=="%VERSION%" (echo invalid NSIS version>&2 & exit /b 2)
echo(%EPOCH%| findstr /r /x "[0-9][0-9]*" >nul || (echo source-date-epoch must be an integer>&2 & exit /b 2)
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

if "%~7"=="" (
  set "WORK=%TEMP%\nsis-upstream-%RANDOM%-%RANDOM%"
  set "CLEANUP=1"
) else (
  for %%I in ("%~7") do set "WORK=%%~fI"
  set "CLEANUP=0"
)
mkdir "%WORK%" 2>nul

set "WINDOWS_NAME=nsis-%VERSION%.zip"
set "SOURCE_NAME=nsis-%VERSION%-src.tar.bz2"
set "BASE_URL=https://sourceforge.net/projects/nsis/files/NSIS%%203/%VERSION%"
set "WINDOWS_URL=%BASE_URL%/%WINDOWS_NAME%/download"
set "SOURCE_URL=%BASE_URL%/%SOURCE_NAME%/download"
set "WINDOWS_FILE=%WORK%\%WINDOWS_NAME%"
set "SOURCE_FILE=%WORK%\%SOURCE_NAME%"

curl.exe -fL --retry 2 --output "%WINDOWS_FILE%" "%WINDOWS_URL%" || goto :download_error
curl.exe -fL --retry 2 --output "%SOURCE_FILE%" "%SOURCE_URL%" || goto :download_error

call :hash "%WINDOWS_FILE%" SHA1 ACTUAL_WINDOWS_SHA1 || goto :hash_error
call :hash "%SOURCE_FILE%" SHA1 ACTUAL_SOURCE_SHA1 || goto :hash_error
if /i not "%ACTUAL_WINDOWS_SHA1%"=="%WINDOWS_SHA1%" (echo Windows archive does not match the upstream-published SHA-1>&2 & goto :failure)
if /i not "%ACTUAL_SOURCE_SHA1%"=="%SOURCE_SHA1%" (echo source archive does not match the upstream-published SHA-1>&2 & goto :failure)
call :hash "%WINDOWS_FILE%" MD5 ACTUAL_WINDOWS_MD5 || goto :hash_error
call :hash "%SOURCE_FILE%" MD5 ACTUAL_SOURCE_MD5 || goto :hash_error
if /i not "%ACTUAL_WINDOWS_MD5%"=="%WINDOWS_MD5%" (echo Windows archive MD5 differs from the published record>&2 & goto :failure)
if /i not "%ACTUAL_SOURCE_MD5%"=="%SOURCE_MD5%" (echo source archive MD5 differs from the published record>&2 & goto :failure)
call :hash "%WINDOWS_FILE%" SHA256 WINDOWS_SHA256 || goto :hash_error
call :hash "%SOURCE_FILE%" SHA256 SOURCE_SHA256 || goto :hash_error
for %%I in ("%WINDOWS_FILE%") do set "WINDOWS_SIZE=%%~zI"
for %%I in ("%SOURCE_FILE%") do set "SOURCE_SIZE=%%~zI"
if not exist "%REPO_ROOT%\config\upstream" mkdir "%REPO_ROOT%\config\upstream"

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
echo         "upstreamPublished": { "sha1": "%ACTUAL_WINDOWS_SHA1%", "md5": "%WINDOWS_MD5%" },
echo         "locallyDerived": { "sha256": "%WINDOWS_SHA256%" }
echo       }
echo     },
echo     "sourceArchive": {
echo       "fileName": "%SOURCE_NAME%",
echo       "url": "%SOURCE_URL%",
echo       "size": %SOURCE_SIZE%,
echo       "digests": {
echo         "upstreamPublished": { "sha1": "%ACTUAL_SOURCE_SHA1%", "md5": "%SOURCE_MD5%" },
echo         "locallyDerived": { "sha256": "%SOURCE_SHA256%" }
echo       }
echo     }
echo   }
echo }
)>"%OUTPUT%"

echo wrote %OUTPUT%
echo review the new file before committing it
call :cleanup
exit /b 0

:hash
set "HASH_LINE="
for /f "tokens=* delims=" %%H in ('certutil.exe -hashfile "%~1" %~2 ^| findstr /r /i /x "[0-9a-f ][0-9a-f ]*"') do if not defined HASH_LINE set "HASH_LINE=%%H"
if not defined HASH_LINE exit /b 1
set "HASH_LINE=%HASH_LINE: =%"
set "%~3=%HASH_LINE%"
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
if "%CLEANUP%"=="1" if defined WORK if exist "%WORK%" rmdir /s /q "%WORK%"
exit /b 0

:usage
echo usage: %~nx0 ^<version^> ^<source-date-epoch^> ^<windows-sha1^> ^<source-sha1^> ^<windows-md5^> ^<source-md5^> [download-dir]>&2
exit /b 2
