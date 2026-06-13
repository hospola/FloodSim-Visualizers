; DanaSim Viewer — NSIS installer script
;
; Lite build (no bundled data, ../publish/DanaSimViewer-Setup-1.0.0-win64.exe):
;   makensis danasim-viewer.nsi
;
; Full build (bundles a data folder as $INSTDIR\data — combined with the empty
; Terrain:BasePath default, the app finds it with zero configuration):
;   makensis -DBUNDLE_DATA -DDATADIR=../../data/data_29_10_2024 danasim-viewer.nsi
;   → ../publish/DanaSimViewer-Setup-1.0.0-full-win64.exe
;
; Note: on Linux, makensis only accepts single-dash options (-D...), not the
; Windows-only "/D..." syntax shown in some NSIS docs.
;
; (run from viewer_net/packaging/)

!include "MUI2.nsh"

; ── Metadata ──────────────────────────────────────────────────────────────────
!define APPNAME    "DanaSim Viewer"
!define APPVERSION "1.0.0"
!define PUBLISHER  "DanaSim"
!define INSTALLDIR "$PROGRAMFILES64\DanaSim Viewer"
!define UNREGKEY   "Software\Microsoft\Windows\CurrentVersion\Uninstall\DanaSim Viewer"
!define SRCDIR     "..\publish\win-x64"

!ifdef BUNDLE_DATA
  !ifndef DATADIR
    !define DATADIR "..\..\data\data_29_10_2024"
  !endif
  !define VARIANT "-full"
!else
  !define VARIANT ""
!endif

Name          "${APPNAME}"
OutFile       "..\publish\DanaSimViewer-Setup-${APPVERSION}${VARIANT}-win64.exe"
InstallDir    "${INSTALLDIR}"
InstallDirRegKey HKLM "Software\DanaSim Viewer" "InstallDir"
RequestExecutionLevel admin

; ── MUI look ──────────────────────────────────────────────────────────────────
!define MUI_ABORTWARNING
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN      "$INSTDIR\start.vbs"
!define MUI_FINISHPAGE_RUN_TEXT "Launch DanaSim Viewer now"
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"

; ── Install ───────────────────────────────────────────────────────────────────
Section "DanaSim Viewer" SecMain
  SetOutPath "$INSTDIR"

  File "${SRCDIR}\DanaSim.Viewer.Web.exe"
  File "${SRCDIR}\aspnetcorev2_inprocess.dll"
  File "${SRCDIR}\web.config"
  File "${SRCDIR}\appsettings.json"
  File "${SRCDIR}\run.bat"
  File "start.vbs"

  SetOutPath "$INSTDIR\wwwroot"
  File /r "${SRCDIR}\wwwroot\*.*"

!ifdef BUNDLE_DATA
  SetOutPath "$INSTDIR\data"
  File /r "${DATADIR}\*.*"
!endif

  ; Start Menu
  CreateDirectory "$SMPROGRAMS\${APPNAME}"
  CreateShortcut  "$SMPROGRAMS\${APPNAME}\${APPNAME}.lnk" \
    "wscript.exe" '"$INSTDIR\start.vbs"' "$INSTDIR\DanaSim.Viewer.Web.exe"
  CreateShortcut  "$SMPROGRAMS\${APPNAME}\Uninstall.lnk" \
    "$INSTDIR\uninstall.exe"

  ; Desktop shortcut
  CreateShortcut "$DESKTOP\${APPNAME}.lnk" \
    "wscript.exe" '"$INSTDIR\start.vbs"' "$INSTDIR\DanaSim.Viewer.Web.exe"

  ; Add/Remove Programs entry
  WriteRegStr   HKLM "${UNREGKEY}" "DisplayName"     "${APPNAME}"
  WriteRegStr   HKLM "${UNREGKEY}" "UninstallString"  "$INSTDIR\uninstall.exe"
  WriteRegStr   HKLM "${UNREGKEY}" "DisplayVersion"   "${APPVERSION}"
  WriteRegStr   HKLM "${UNREGKEY}" "Publisher"        "${PUBLISHER}"
  WriteRegDWORD HKLM "${UNREGKEY}" "NoModify" 1
  WriteRegDWORD HKLM "${UNREGKEY}" "NoRepair"  1

  WriteUninstaller "$INSTDIR\uninstall.exe"
SectionEnd

; ── Uninstall ─────────────────────────────────────────────────────────────────
Section "Uninstall"
  Delete "$INSTDIR\DanaSim.Viewer.Web.exe"
  Delete "$INSTDIR\aspnetcorev2_inprocess.dll"
  Delete "$INSTDIR\web.config"
  Delete "$INSTDIR\appsettings.json"
  Delete "$INSTDIR\run.bat"
  Delete "$INSTDIR\start.vbs"
  Delete "$INSTDIR\uninstall.exe"
  RMDir /r "$INSTDIR\wwwroot"
!ifdef BUNDLE_DATA
  RMDir /r "$INSTDIR\data"
!endif
  RMDir  "$INSTDIR"

  Delete "$DESKTOP\${APPNAME}.lnk"
  Delete "$SMPROGRAMS\${APPNAME}\${APPNAME}.lnk"
  Delete "$SMPROGRAMS\${APPNAME}\Uninstall.lnk"
  RMDir  "$SMPROGRAMS\${APPNAME}"

  DeleteRegKey HKLM "${UNREGKEY}"
  DeleteRegKey HKLM "Software\DanaSim Viewer"
SectionEnd
