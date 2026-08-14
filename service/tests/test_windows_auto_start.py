from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"


def test_start_script_defines_safe_service_runtime() -> None:
    script = (SCRIPTS_DIR / "start-service.ps1").read_text(encoding="utf-8")

    assert "param(" in script
    assert "[string]$ApiKeyFile" in script
    assert "$PSScriptRoot" in script
    assert "Test-Path -LiteralPath" in script
    assert "$env:DIFY_AGENT_WORKSPACE_ROOT" in script
    assert "$env:DIFY_AGENT_WORKSPACE_PERMISSIONS_DB" in script
    assert "$env:DIFY_AGENT_WORKSPACE_API_KEY_FILE" in script
    assert "service.app.main:app" in script
    for argument in ('"--host"', '"0.0.0.0"', '"--port"', '"8890"'):
        assert argument in script
    assert "Start-Process" in script
    assert "-RedirectStandardOutput" in script
    assert "-RedirectStandardError" in script
    assert "-WindowStyle Hidden" in script
    assert "-Wait" in script
    assert "-NoNewWindow" not in script
    assert "*>>" not in script
    assert "DIFY_AGENT_WORKSPACE_API_KEY=" not in script
    assert "Get-Content" not in script


def test_install_script_registers_one_logon_task_without_secret_value() -> None:
    script = (SCRIPTS_DIR / "install-auto-start.ps1").read_text(encoding="utf-8")

    assert '$taskName = "DifyAgentWorkspaceTools"' in script
    assert "New-ScheduledTaskAction" in script
    assert "New-ScheduledTaskTrigger -AtLogOn" in script
    assert "New-ScheduledTaskSettingsSet" in script
    assert "-RestartCount 3" in script
    assert "Register-ScheduledTask" in script
    assert "-Force" in script
    assert "-ApiKeyFile" in script
    assert "Get-Content" not in script
    assert "DIFY_AGENT_WORKSPACE_API_KEY=" not in script


def test_uninstall_script_removes_only_the_fixed_task() -> None:
    script = (SCRIPTS_DIR / "uninstall-auto-start.ps1").read_text(
        encoding="utf-8"
    )

    assert '$taskName = "DifyAgentWorkspaceTools"' in script
    assert "Get-ScheduledTask -TaskName $taskName" in script
    assert "Unregister-ScheduledTask" in script
    assert "-Confirm:$false" in script
    assert "Remove-Item" not in script
