Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

silent = False
For Each arg In WScript.Arguments
    If LCase(arg) = "/silent" Then silent = True
Next

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
exePath = scriptDir & "\dist\QuickXe\QuickXe.exe"
iconPath = scriptDir & "\quickxe.ico"

If Not fso.FileExists(exePath) Then
    msg = "QuickXe.exe not found at:" & vbCrLf & exePath & vbCrLf & vbCrLf & _
          "Run install.bat first to build it."
    If silent Then WScript.Echo msg Else MsgBox msg, vbExclamation, "QuickXe"
    WScript.Quit 1
End If

desktopPath = WshShell.SpecialFolders("Desktop")
shortcutPath = desktopPath & "\QuickXe.lnk"

Set lnk = WshShell.CreateShortcut(shortcutPath)
lnk.TargetPath = exePath
lnk.WorkingDirectory = scriptDir & "\dist\QuickXe"
lnk.IconLocation = iconPath
lnk.Description = "QuickXe - launch your games"
lnk.Save

If Not silent Then
    MsgBox "Desktop shortcut created!" & vbCrLf & vbCrLf & shortcutPath, _
           vbInformation, "QuickXe"
End If
