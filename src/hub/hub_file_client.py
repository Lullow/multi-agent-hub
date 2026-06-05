import time
from typing import Any

import requests

from src.hub.hub_config import HUB_AGENT_NAME, HUB_BASE_URL, HUB_PASSWORD


REQUEST_TIMEOUT_SECONDS = 10
MIN_REQUEST_INTERVAL_SECONDS = 1.0

_last_request_at = 0.0


def _rate_limited_request(method: str, path: str, **kwargs: Any) -> requests.Response:
    """
    Send a hub request while respecting the one-request-per-second limit.
    """

    global _last_request_at

    elapsed = time.monotonic() - _last_request_at

    if elapsed < MIN_REQUEST_INTERVAL_SECONDS:
        time.sleep(MIN_REQUEST_INTERVAL_SECONDS - elapsed)

    response = requests.request(
        method,
        f"{HUB_BASE_URL}{path}",
        timeout=REQUEST_TIMEOUT_SECONDS,
        **kwargs,
    )
    _last_request_at = time.monotonic()

    response.raise_for_status()
    return response


def fetch_messages(since: int = 0) -> list[dict]:
    """
    Fetch chat messages from the shared hub.
    """

    response = _rate_limited_request(
        "GET",
        "/api/messages",
        params={
            "since": since,
            "password": HUB_PASSWORD,
        },
    )
    data = response.json()

    if isinstance(data, list):
        return data

    return data.get("messages", [])


def post_chat_message(content: str) -> int | None:
    """
    Post a coordination message to the shared hub chat.
    """

    response = _rate_limited_request(
        "POST",
        "/api/message",
        json={
            "agent_name": HUB_AGENT_NAME,
            "content": content,
            "role": "developer",
            "password": HUB_PASSWORD,
        },
    )
    data = response.json()

    if isinstance(data, dict):
        return data.get("seq")

    return None


def fetch_billboard() -> dict:
    """
    Fetch the shared billboard if the hub provides one.
    """

    response = _rate_limited_request(
        "GET",
        "/api/billboard",
        params={
            "password": HUB_PASSWORD,
        },
    )
    data = response.json()

    if isinstance(data, dict):
        return data

    return {"content": data}


def list_files() -> list[dict]:
    """
    List files available in the shared hub file store.
    """

    response = _rate_limited_request(
        "GET",
        "/api/files",
        params={
            "password": HUB_PASSWORD,
        },
    )
    data = response.json()

    if isinstance(data, list):
        return data

    files = data.get("files", [])

    if isinstance(files, list):
        return files

    return []


def upload_file(filename: str, content: str) -> dict:
    """
    Upload a file to the shared hub file store.
    """

    response = _rate_limited_request(
        "POST",
        "/api/files",
        json={
            "agent_name": HUB_AGENT_NAME,
            "filename": filename,
            "content": content,
            "password": HUB_PASSWORD,
        },
    )
    data = response.json()

    if isinstance(data, dict):
        return data

    return {"result": data}


def get_file_name(file_info: dict) -> str:
    """
    Extract a shared file name across likely hub response shapes.
    """

    for key in ("filename", "name", "path", "file_name"):
        value = file_info.get(key)

        if isinstance(value, str) and value:
            return value

    return ""


def get_file_content(file_info: dict) -> str:
    """
    Extract shared file content across likely hub response shapes.
    """

    for key in ("content", "text", "body"):
        value = file_info.get(key)

        if isinstance(value, str):
            return value

    return ""


def read_shared_file(filename: str) -> str | None:
    """
    Read a file from the shared file list by name.
    """

    for file_info in list_files():
        if get_file_name(file_info) == filename:
            return get_file_content(file_info)

    return None
