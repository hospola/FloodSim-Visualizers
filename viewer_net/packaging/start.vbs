Set WshShell = CreateObject("WScript.Shell")
Set objFSO   = CreateObject("Scripting.FileSystemObject")
strDir = objFSO.GetParentFolderName(WScript.ScriptFullName)
WshShell.Run Chr(34) & strDir & "\run.bat" & Chr(34), 0
Set WshShell = Nothing
Set objFSO   = Nothing
