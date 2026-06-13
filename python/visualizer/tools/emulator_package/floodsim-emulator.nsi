; Self-extracting, single-file Windows launcher for the DanaSim MQTT emulator.
;
; Bundles a Python 3.11 embeddable runtime + paho-mqtt + emulator_app.py +
; recording.jsonl. On run, it silently extracts itself to %TEMP% and
; launches the emulator, forwarding any command-line arguments.

!include "FileFunc.nsh"

Unicode true
Name "FloodSim Emulator"
OutFile "dist\floodsim-emulator.exe"
SilentInstall silent
RequestExecutionLevel user
InstallDir "$TEMP\floodsim-emulator"

Section
  SetOutPath "$INSTDIR"
  File /r "windows_build\payload\*.*"

  ${GetParameters} $R0

  ExecWait '"$INSTDIR\python\python.exe" "$INSTDIR\emulator_app.py" $R0' $0
SectionEnd
