Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "python """ & Replace(WScript.ScriptFullName, WScript.ScriptName, "") & "bot.py""", 0, False
