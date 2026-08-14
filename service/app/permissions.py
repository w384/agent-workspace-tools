import sqlite3
from pathlib import Path
from typing import Any


def initialize_database(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS employees (
                user_id TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                business_unit TEXT NOT NULL,
                department TEXT NOT NULL,
                position TEXT NOT NULL,
                enabled INTEGER NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS employee_path_prefixes (
                user_id TEXT NOT NULL,
                path_prefix TEXT NOT NULL,
                PRIMARY KEY (user_id, path_prefix),
                FOREIGN KEY (user_id) REFERENCES employees(user_id)
            )
            """
        )


def upsert_employee(
    database_path: Path,
    *,
    user_id: str,
    email: str,
    business_unit: str,
    department: str,
    position: str,
    enabled: bool,
) -> None:
    initialize_database(database_path)

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO employees (
                user_id,
                email,
                business_unit,
                department,
                position,
                enabled
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                email = excluded.email,
                business_unit = excluded.business_unit,
                department = excluded.department,
                position = excluded.position,
                enabled = excluded.enabled
            """,
            (
                user_id,
                email,
                business_unit,
                department,
                position,
                int(enabled),
            ),
        )


def add_path_prefix(
    database_path: Path,
    *,
    user_id: str,
    path_prefix: str,
) -> None:
    initialize_database(database_path)

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT OR IGNORE INTO employee_path_prefixes (
                user_id,
                path_prefix
            )
            VALUES (?, ?)
            """,
            (user_id, path_prefix),
        )


def get_user_permissions(
    database_path: Path,
    *,
    user_id: str,
) -> dict[str, Any]:
    initialize_database(database_path)

    with sqlite3.connect(database_path) as connection:
        employee = connection.execute(
            """
            SELECT
                user_id,
                email,
                business_unit,
                department,
                position,
                enabled
            FROM employees
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()

        if employee is None:
            raise ValueError("未找到用户权限")

        prefixes = connection.execute(
            """
            SELECT path_prefix
            FROM employee_path_prefixes
            WHERE user_id = ?
            ORDER BY path_prefix
            """,
            (user_id,),
        ).fetchall()

    return {
        "user_id": employee[0],
        "email": employee[1],
        "business_unit": employee[2],
        "department": employee[3],
        "position": employee[4],
        "enabled": bool(employee[5]),
        "path_prefixes": [row[0] for row in prefixes],
    }

def is_path_allowed(
    path_prefixes: list[str],
    relative_path: str,
) -> bool:
    normalized_path = relative_path.replace("\\", "/").strip("/")

    if not normalized_path:
        return "" in path_prefixes

    path_parts = normalized_path.split("/")

    if any(
        part in {"", ".", ".."}
        for part in path_parts
    ):
        return False

    if ":" in normalized_path or normalized_path.startswith("/"):
        return False

    for prefix in path_prefixes:
        normalized_prefix = prefix.replace("\\", "/").strip("/")

        if not normalized_prefix:
            return True

        prefix_parts = normalized_prefix.split("/")

        if any(
            part in {"", ".", ".."}
            for part in prefix_parts
        ):
            continue

        if path_parts[:len(prefix_parts)] == prefix_parts:
            return True

    return False


def filter_allowed_paths(
    path_prefixes: list[str],
    paths: list[str],
) -> list[str]:
    return [
        path
        for path in paths
        if is_path_allowed(path_prefixes, path)
    ]