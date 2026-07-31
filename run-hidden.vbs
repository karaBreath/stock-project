' NEBULA / Trade World News - start the app with no console window at all.
'
' Run(cmd, 0, False): 0 = hidden window, False = do not wait for it to end.
' This is what makes autostart invisible - without it every logon would
' flash a black window and leave it sitting on the taskbar.
'
' The folder is worked out from this file's own location rather than
' hardcoded, so moving the project folder does not silently break autostart.
'
' ASCII only on purpose - cscript reads .vbs using the system ANSI code page,
' so Thai text here would arrive mangled.
Dim fso, here
Set fso = CreateObject("Scripting.FileSystemObject")
here = fso.GetParentFolderName(WScript.ScriptFullName)
CreateObject("WScript.Shell").Run _
  Chr(34) & here & "\autostart-run.bat" & Chr(34), 0, False
