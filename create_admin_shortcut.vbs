Set objShell = CreateObject("WScript.Shell")
Set objShortcut = objShell.CreateShortcut(objShell.SpecialFolders("Desktop") & "\ScreenShare Host (Admin).lnk")

' Set the target to the batch file
objShortcut.TargetPath = objShell.CurrentDirectory & "\host.bat"
objShortcut.WorkingDirectory = objShell.CurrentDirectory

' Set to run as administrator
objShortcut.WindowStyle = 1

' Save the shortcut
objShortcut.Save

' Set the shortcut to run as administrator using PowerShell
Set objFSO = CreateObject("Scripting.FileSystemObject")
shortcutPath = objShell.SpecialFolders("Desktop") & "\ScreenShare Host (Admin).lnk"

' Use PowerShell to set the RunAsAdmin flag
powershellCmd = "powershell -Command ""$shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut('" & shortcutPath & "'); $shortcut.TargetPath = '" & objShell.CurrentDirectory & "\host.bat'; $shortcut.WorkingDirectory = '" & objShell.CurrentDirectory & "'; $shortcut.Save(); $bytes = [System.IO.File]::ReadAllBytes('" & shortcutPath & "'); $bytes[0x15] = $bytes[0x15] -bor 0x20; [System.IO.File]::WriteAllBytes('" & shortcutPath & "', $bytes)"""

objShell.Run powershellCmd, 0, True

WScript.Echo "Admin shortcut created on desktop!" 