' DSH 桌面壳 - 双击启动（无控制台窗口）
' 用法：双击本文件即可启动桌面端（不弹出 cmd 黑窗口）
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
base = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = base
shell.Run """node_modules\electron\dist\electron.exe"" . --no-sandbox", 0, False
