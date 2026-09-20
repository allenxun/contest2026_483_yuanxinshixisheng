$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

$process = Get-Process -Name vmware | Where-Object { $_.MainWindowTitle -like '*Ubuntu 22.04*' } | Select-Object -First 1
if (-not $process) { throw 'VMware window not found' }
$root = [System.Windows.Automation.AutomationElement]::FromHandle($process.MainWindowHandle)
$walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker

function Show-Tree([System.Windows.Automation.AutomationElement]$node, [int]$depth) {
  if ($depth -gt 5) { return }
  $current = $walker.GetFirstChild($node)
  while ($null -ne $current) {
    $name = $current.Current.Name
    $type = $current.Current.ControlType.ProgrammaticName
    $id = $current.Current.AutomationId
    if ($name -or $id) {
      Write-Output ((('  ' * $depth) + $type + ' | ' + $name + ' | ' + $id))
    }
    Show-Tree $current ($depth + 1)
    $current = $walker.GetNextSibling($current)
  }
}

Write-Output ('WINDOW | ' + $root.Current.Name)
Show-Tree $root 0
