' create_shortcut.vbs
' Creates a desktop shortcut for QuickXe.exe using the heart-lock icon.
' Called by install.bat, or can be double-clicked standalone.

Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

' Detect if running silently (e.g. from cscript inside install.bat)
silent = False
For Each arg In WScript.Arguments
    If LCase(arg) = "/silent" Then silent = True
Next

' Resolve paths relative to this script's folder
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
exePath = scriptDir & "\dist\QuickXe.exe"
iconPath = scriptDir & "\quickxe.ico"

If Not fso.FileExists(exePath) Then
    msg = "QuickXe.exe not found at:" & vbCrLf & exePath & vbCrLf & vbCrLf & _
          "Run install.bat first to build it."
    If silent Then
        WScript.Echo msg
    Else
        MsgBox msg, vbExclamation, "QuickXe"
    End If
    WScript.Quit 1
End If

desktopPath = WshShell.SpecialFolders("Desktop")
shortcutPath = desktopPath & "\QuickXe.lnk"

Set lnk = WshShell.CreateShortcut(shortcutPath)
lnk.TargetPath = exePath
lnk.WorkingDirectory = scriptDir & "\dist"
lnk.IconLocation = iconPath
lnk.Description = "QuickXe - launch your games"
lnk.Save

If Not silent Then
    MsgBox "Desktop shortcut created!" & vbCrLf & vbCrLf & shortcutPath, _
           vbInformation, "QuickXe"
End If
