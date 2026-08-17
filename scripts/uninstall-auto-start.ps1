[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$taskName = "AgentWorkspaceTools"
$task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue

if ($null -ne $task) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Output "Scheduled task '$taskName' was removed."
}
else {
    Write-Output "Scheduled task '$taskName' is not installed."
}
