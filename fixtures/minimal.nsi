Unicode true
Name "NsisToolset smoke test"
OutFile "smoke-installer.exe"
RequestExecutionLevel user
SilentInstall silent
SilentUnInstall silent

Section
  SetOutPath "$TEMP\\NsisToolsetSmoke"
  FileOpen $0 "$TEMP\\NsisToolsetSmoke\\installed.txt" w
  FileWrite $0 "installed"
  FileClose $0
  WriteUninstaller "$TEMP\\NsisToolsetSmoke\\uninstall.exe"
SectionEnd

Section "Uninstall"
  Delete "$TEMP\\NsisToolsetSmoke\\installed.txt"
  Delete "$TEMP\\NsisToolsetSmoke\\uninstall.exe"
  RMDir "$TEMP\\NsisToolsetSmoke"
SectionEnd

