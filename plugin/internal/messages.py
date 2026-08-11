import re


SERVICE_TIMEOUT_MESSAGE = "本机文件服务响应超时"
SERVICE_CONNECTION_MESSAGE = "本机文件服务连接失败"
INVALID_SERVICE_RESPONSE_MESSAGE = "本机文件服务返回了无法解析的响应"
SERVICE_REQUEST_FAILED_MESSAGE = "本机文件服务请求失败"

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
) -> str:
    """Return a service message only when it contains no local secrets."""
    text = str(message) if message else fallback
    if api_key and api_key in text:
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
