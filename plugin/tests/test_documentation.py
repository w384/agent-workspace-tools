from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_workflow_docs_define_safe_natural_language_and_approval_flows() -> None:
    workflow = (PROJECT_ROOT / "docs" / "dify" / "workflow-setup.md").read_text(
        encoding="utf-8"
    )
    cases = (PROJECT_ROOT / "docs" / "dify" / "acceptance-cases.md").read_text(
        encoding="utf-8"
    )
    plugin_readme = (PROJECT_ROOT / "plugin" / "README.md").read_text(
        encoding="utf-8"
    )
    manifest = yaml.safe_load(
        (PROJECT_ROOT / "plugin" / "manifest.yaml").read_text(encoding="utf-8")
    )
    combined = "\n".join((workflow, cases, plugin_readme))

    for tool_name in (
        "list_files",
        "search_files",
        "get_file",
        "upload_file",
        "create_plan",
        "execute_confirmed_plan",
    ):
        assert tool_name in combined
    assert "host.docker.internal:8890" in combined
    assert "Human Input" in combined
    assert "成功案例" in cases
    assert "失败案例" in cases
    assert "X-API-Key: <" not in combined
    assert manifest["version"] == "0.0.6"
    assert manifest["meta"]["version"] == "0.0.6"
    assert "**Version:** 0.0.6" in plugin_readme
    assert "Replace the placeholder" not in plugin_readme


def test_exported_workflow_keeps_llm_planning_before_human_approval() -> None:
    exported_workflow = yaml.safe_load(
        (
            PROJECT_ROOT
            / "docs"
            / "dify"
            / "local-workspace-tools-permission-demo-v0.0.6.yml"
        ).read_text(encoding="utf-8")
    )
    nodes = exported_workflow["workflow"]["graph"]["nodes"]
    edges = {
        (edge["source"], edge["target"])
        for edge in exported_workflow["workflow"]["graph"]["edges"]
    }
    nodes_by_type = {
        node["data"]["type"]: node
        for node in nodes
    }
    llm_node = nodes_by_type["llm"]
    start_node = nodes_by_type["start"]
    list_node = next(
        node
        for node in nodes
        if node["data"]["title"] == "列出工作区文件"
    )
    plan_node = next(
        node
        for node in nodes
        if node["data"]["title"] == "创建工作区计划"
    )
    human_input_node = nodes_by_type["human-input"]
    execute_node = next(
        node
        for node in nodes
        if node["data"]["title"] == "执行已确认计划"
    )
    llm_system_prompt = next(
        message["text"]
        for message in llm_node["data"]["prompt_template"]
        if message["role"] == "system"
    )
    llm_user_prompt = next(
        message["text"]
        for message in llm_node["data"]["prompt_template"]
        if message["role"] == "user"
    )

    assert start_node["data"]["variables"] == [
        {
            "default": "",
            "hint": "",
            "label": "文件整理需求",
            "options": [],
            "placeholder": "",
            "required": True,
            "type": "paragraph",
            "variable": "request",
        }
    ]
    assert llm_node["data"]["model"]["completion_params"]["think"] is False
    assert llm_node["data"]["model"]["completion_params"]["num_predict"] == 2000
    assert all(
        key not in llm_system_prompt
        for key in ("行动", "目的地", "来源")
    )
    assert all(
        operation in llm_system_prompt
        for operation in ("create_folder", "move_rename", "trash")
    )
    assert f"{{{{#{start_node['id']}.request#}}}}" in llm_user_prompt
    assert f"{{{{#{list_node['id']}.text#}}}}" in llm_user_prompt
    assert plan_node["data"]["tool_parameters"]["operations_json"] == {
        "type": "mixed",
        "value": f"{{{{#{llm_node['id']}.text#}}}}",
    }
    assert (list_node["id"], llm_node["id"]) in edges
    assert (llm_node["id"], plan_node["id"]) in edges
    assert (plan_node["id"], human_input_node["id"]) in edges
    assert (human_input_node["id"], execute_node["id"]) in edges
