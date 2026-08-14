[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ApiKeyFile
)

$ErrorActionPreference = "Stop"
$taskName = "DifyAgentWorkspaceTools"
$startScript = Join-Path $PSScriptRoot "start-service.ps1"

foreach ($requiredPath in @($startScript, $ApiKeyFile)) {
    if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
        throw "Required file does not exist: $requiredPath"
    }
}

$resolvedStartScript = (Resolve-Path -LiteralPath $startScript).Path
$resolvedApiKeyFile = (Resolve-Path -LiteralPath $ApiKeyFile).Path
$currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$arguments = "-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$resolvedStartScript`" -ApiKeyFile `"$resolvedApiKeyFile`""

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $arguments
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $currentUser
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartInterval (New-TimeSpan -Minutes 1) -RestartCount 3 -ExecutionTimeLimit (New-TimeSpan -Days 1)
$principal = New-ScheduledTaskPrincipal -UserId $currentUser -LogonType Interactive -RunLevel Limited
$task = New-ScheduledTask -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description "Start Dify Agent Workspace Tools after user logon."

Register-ScheduledTask -TaskName $taskName -InputObject $task -Force | Out-Null
Write-Output "Scheduled task '$taskName' is installed for $currentUser."
