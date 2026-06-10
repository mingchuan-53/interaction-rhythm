' 交互节律 — 静默启动（无终端窗口）
' 用于开机自启动和快捷方式
Set fso = CreateObject("Scripting.FileSystemObject")
Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.Run "cmd /c .venv\Scripts\python.exe main.py", 0, False
