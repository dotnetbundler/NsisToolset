Unicode true
Name "NsisToolset smoke test"
OutFile "smoke-installer.exe"
RequestExecutionLevel user
SilentInstall silent
SilentUnInstall silent
InstallDir "$TEMP\NsisToolsetSmoke"

Section
  SetOutPath "$INSTDIR"
  FileOpen $0 "$INSTDIR\installed.txt" w
  FileWrite $0 "installed"
  FileClose $0
  WriteUninstaller "$INSTDIR\uninstall.exe"
SectionEnd

Section "Uninstall"
  Delete "$INSTDIR\installed.txt"
  Delete "$INSTDIR\uninstall.exe"
  RMDir "$INSTDIR"
SectionEnd
