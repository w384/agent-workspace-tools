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
