$ErrorActionPreference = 'Stop'
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;

[ComImport, InterfaceType(ComInterfaceType.InterfaceIsIUnknown), Guid("a5cd92ff-29be-454c-8d04-d82879fb3f1b")]
interface IVirtualDesktopManager {
  int IsWindowOnCurrentVirtualDesktop(IntPtr topLevelWindow, out int onCurrentDesktop);
  int GetWindowDesktopId(IntPtr topLevelWindow, out Guid desktopId);
  int MoveWindowToDesktop(IntPtr topLevelWindow, ref Guid desktopId);
}

[ComImport, Guid("aa509086-5ca9-4c25-8f95-589d3c07b48a")]
class VirtualDesktopManager {}

public static class DesktopProbe {
  public static string Inspect(IntPtr hwnd) {
    var manager = (IVirtualDesktopManager)new VirtualDesktopManager();
    int current;
    Guid id;
    int hrCurrent = manager.IsWindowOnCurrentVirtualDesktop(hwnd, out current);
    int hrId = manager.GetWindowDesktopId(hwnd, out id);
    return "current=" + current + " hrCurrent=" + hrCurrent + " desktop=" + id + " hrId=" + hrId;
  }
}
'@

$process = Get-Process -Name vmware | Where-Object { $_.MainWindowTitle -like '*Ubuntu 22.04*' } | Select-Object -First 1
if (-not $process) { throw 'VMware window not found' }
[DesktopProbe]::Inspect($process.MainWindowHandle)
