import importlib
from pathlib import Path


def test_get_user_permissions_returns_authorized_prefixes(
    tmp_path: Path,
):
    permissions_module = importlib.import_module(
        "service.app.permissions"
    )

    database_path = tmp_path / "permissions.db"

    permissions_module.initialize_database(database_path)

    permissions_module.upsert_employee(
        database_path,
        user_id="admin-user",
        email="admin@example.com",
        business_unit="技术事业部",
        department="平台工程部",
        position="管理员",
        enabled=True,
    )

    permissions_module.add_path_prefix(
        database_path,
        user_id="admin-user",
        path_prefix="",
    )

    result = permissions_module.get_user_permissions(
        database_path,
        user_id="admin-user",
    )

    assert result["user_id"] == "admin-user"
    assert result["enabled"] is True
    assert result["path_prefixes"] == [""]


def test_path_prefix_matching_respects_directory_boundaries():
    permissions_module = importlib.import_module(
        "service.app.permissions"
    )

    assert permissions_module.is_path_allowed(
        [""],
        "any/path.txt",
    ) is True

    assert permissions_module.is_path_allowed(
        ["1"],
        "1/report.txt",
    ) is True

    assert permissions_module.is_path_allowed(
        ["1"],
        "1/sub/report.txt",
    ) is True

    assert permissions_module.is_path_allowed(
        ["1"],
        "10/report.txt",
    ) is False

    assert permissions_module.is_path_allowed(
        ["1"],
        "report.txt",
    ) is False


def test_filter_paths_returns_only_authorized_files():
    permissions_module = importlib.import_module(
        "service.app.permissions"
    )

    paths = [
        "1/report.txt",
        "1/sub/notes.txt",
        "10/other.txt",
        "root.txt",
    ]

    result = permissions_module.filter_allowed_paths(
        ["1"],
        paths,
    )

    assert result == [
        "1/report.txt",
        "1/sub/notes.txt",
    ]


def filter_allowed_paths(
    path_prefixes: list[str],
    paths: list[str],
) -> list[str]:
    return [
        path
        for path in paths
        if is_path_allowed(path_prefixes, path)
    ]