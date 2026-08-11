from pathlib import Path

import pytest
from dify_plugin import Tool
from dify_plugin.core.utils.class_loader import (
    load_single_subclass_from_source,
)


@pytest.mark.parametrize(
    ("tool_name", "expected_class_name"),
    [
        ("list_files", "ListFilesTool"),
        ("search_files", "SearchFilesTool"),
        ("get_file", "GetFileTool"),
        ("create_plan", "CreatePlanTool"),
        (
            "execute_confirmed_plan",
            "ExecuteConfirmedPlanTool",
        ),
    ],
)
def test_each_tool_source_exposes_exactly_one_tool_subclass(
    tool_name: str,
    expected_class_name: str,
) -> None:
    plugin_root = Path(__file__).resolve().parents[1]
    tool_file = plugin_root / "tools" / f"{tool_name}.py"

    tool_class = load_single_subclass_from_source(
        module_name=f"_runtime_{tool_name}",
        script_path=str(tool_file),
        parent_type=Tool,
    )

    assert tool_class.__name__ == expected_class_name