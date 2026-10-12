Option Explicit
Dim shell, fso, base, runtime, script
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
base = fso.GetParentFolderName(WScript.ScriptFullName)
script = base & "\tools\companion_gui.pyw"
runtime = shell.ExpandEnvironmentStrings("%USERPROFILE%") & "\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\pythonw.exe"
If Not fso.FileExists(runtime) Then runtime = "pythonw.exe"
shell.Run """" & runtime & """ """ & script & """", 0, False
