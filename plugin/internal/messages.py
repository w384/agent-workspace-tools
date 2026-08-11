import re


SERVICE_TIMEOUT_MESSAGE = "本机文件服务响应超时"
SERVICE_CONNECTION_MESSAGE = "本机文件服务连接失败"
INVALID_SERVICE_RESPONSE_MESSAGE = "本机文件服务返回了无法解析的响应"
SERVICE_REQUEST_FAILED_MESSAGE = "本机文件服务请求失败"
EXECUTION_STATUS_UNCERTAIN_MESSAGE = (
    "执行状态不确定：请重新查询计划状态或扫描工作区，"
    "禁止重复提交执行请求"
)

_WINDOWS_ABSOLUTE_PATH = re.compile(r"(?i)(?<![\w])(?:[a-z]:[\\/])")
_WINDOWS_UNC_PATH = re.compile(r"(?<![\\\w])\\\\[^\\\s]+\\[^\\\s]+")
_WINDOWS_ROOTED_PATH = re.compile(
    r"(?<![\\\w])\\(?!\\)[^\\\s]+(?:\\[^\\\s]+)+"
)
_POSIX_ABSOLUTE_PATH = re.compile(r"(?<![:\w])/(?:[^\s/]+/)*[^\s/]+")


def safe_service_message(
    message: object,
    *,
    api_key: str,
    fallback: str = SERVICE_REQUEST_FAILED_MESSAGE,
    secrets: tuple[str, ...] = (),
) -> str:
    """Return a service message only when it contains no local secrets."""
    text = str(message) if message else fallback
    if api_key and api_key in text:
        return fallback
    if any(secret and secret in text for secret in secrets):
        return fallback
    if (
        _WINDOWS_ABSOLUTE_PATH.search(text)
        or _WINDOWS_UNC_PATH.search(text)
        or _WINDOWS_ROOTED_PATH.search(text)
        or _POSIX_ABSOLUTE_PATH.search(text)
    ):
        return fallback
    return text


def format_file_page(result: dict[str, object]) -> str:
    total = int(result["total"])
    page = int(result["page"])
    page_size = int(result["page_size"])
    files = result["files"]
    if not isinstance(files, list):
        raise ValueError("文件列表响应格式无效")
    if not files:
        return f"共找到 {total} 个文件；第 {page} 页没有文件。"

    lines = [f"共找到 {total} 个文件（第 {page} 页，每页 {page_size} 个）："]
    for item in files:
        if not isinstance(item, dict):
            raise ValueError("文件列表响应格式无效")
        lines.append(
            f"- {item['path']}（{item['size_bytes']} 字节，"
            f"修改时间：{item['modified_at']}）"
        )
    return "\n".join(lines)


def format_file_detail(result: dict[str, object]) -> str:
    path = result["path"]
    size_bytes = result["size_bytes"]
    if result.get("content_base64") is None:
        return (
            f"文件 {path} 超过 15MB，已仅返回元数据，"
            "未返回文件内容。"
        )
    return (
        f"已读取文件 {path}（{size_bytes} 字节），"
        "内容已作为 Base64 返回。"
    )


def format_plan_confirmation(result: dict[str, object]) -> str:
    confirmation = result["confirmation"]
    if not isinstance(confirmation, dict):
        raise ValueError("计划确认响应格式无效")

    required_sections = (
        "folders_to_create",
        "moves",
        "renames",
        "trash",
    )
    if set(confirmation) != set(required_sections):
        raise ValueError("计划确认响应格式无效")

    folders = confirmation["folders_to_create"]
    moves = confirmation["moves"]
    renames = confirmation["renames"]
    trash = confirmation["trash"]
    if not all(isinstance(items, list) for items in (folders, moves, renames, trash)):
        raise ValueError("计划确认响应格式无效")
    if not all(isinstance(item, str) and item for item in folders):
        raise ValueError("计划确认响应格式无效")
    if not all(isinstance(item, str) and item for item in trash):
        raise ValueError("计划确认响应格式无效")
    if not all(
        isinstance(item, dict)
        and isinstance(item.get("source"), str)
        and bool(item["source"])
        and isinstance(item.get("destination"), str)
        and bool(item["destination"])
        for item in moves
    ):
        raise ValueError("计划确认响应格式无效")
    if not all(
        isinstance(item, dict)
        and isinstance(item.get("source_name"), str)
        and bool(item["source_name"])
        and isinstance(item.get("destination_name"), str)
        and bool(item["destination_name"])
        for item in renames
    ):
        raise ValueError("计划确认响应格式无效")

    folder_text = "、".join(folders) or "无"
    move_text = "；".join(
        f"{item['source']} → {item['destination']}"
        for item in moves
    ) or "无"
    rename_text = "；".join(
        f"{item['source_name']} → {item['destination_name']}"
        for item in renames
    ) or "无"
    trash_text = "、".join(trash) or "无"

    return "\n".join(
        (
            f"计划编号：{result['plan_id']}",
            f"文件数量：{result['file_count']}",
            f"新建文件夹：{folder_text}",
            f"移动明细：{move_text}",
            f"重命名明细：{rename_text}",
            f"回收明细：{trash_text}",
        )
    )


def format_execution_result(result: dict[str, object]) -> str:
    return (
        f"计划 {result['plan_id']} 已执行完成，共处理 "
        f"{result['file_count']} 个文件，操作编号："
        f"{result['operation_id']}。"
    )
