[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ApiKeyFile
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot "service\.venv\Scripts\python.exe"
$workspaceRoot = "D:\AI\AgentWorkspace"
$permissionsDatabase = Join-Path $workspaceRoot ".file-manager\permissions.db"
$logDirectory = Join-Path $workspaceRoot ".file-manager\logs"
$standardOutputLog = Join-Path $logDirectory "service.stdout.log"
$standardErrorLog = Join-Path $logDirectory "service.stderr.log"

foreach ($requiredPath in @($pythonPath, $ApiKeyFile, $workspaceRoot, $permissionsDatabase)) {
    if (-not (Test-Path -LiteralPath $requiredPath)) {
        throw "Required path does not exist: $requiredPath"
    }
}

New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null

$env:DIFY_AGENT_WORKSPACE_ROOT = $workspaceRoot
$env:DIFY_AGENT_WORKSPACE_PERMISSIONS_DB = $permissionsDatabase
$env:DIFY_AGENT_WORKSPACE_API_KEY_FILE = (Resolve-Path -LiteralPath $ApiKeyFile).Path
$env:PYTHONUNBUFFERED = "1"

Push-Location $projectRoot
try {
    $serviceProcess = Start-Process `
        -FilePath $pythonPath `
        -ArgumentList @("-m", "uvicorn", "service.app.main:app", "--host", "0.0.0.0", "--port", "8890") `
        -RedirectStandardOutput $standardOutputLog `
        -RedirectStandardError $standardErrorLog `
        -WindowStyle Hidden `
        -Wait `
        -PassThru
    exit $serviceProcess.ExitCode
}
finally {
    Pop-Location
}
