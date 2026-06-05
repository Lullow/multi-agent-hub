import json
from dataclasses import dataclass, field
from typing import Any

from src.hub.hub_config import HUB_DRY_RUN
from src.hub.hub_file_client import (
    get_file_name,
    list_files,
    post_chat_message,
    read_shared_file,
    upload_file as upload_shared_file,
)
from src.hub.hub_response_guard import BLOCKED_RESPONSE_PATTERNS, sanitize_hub_response


MAX_CHAT_MESSAGE_CHARS = 1200


@dataclass
class HubToolState:
    """
    Runtime state for one tool-agent run.

    read_files tracks shared files read during this run so the agent cannot
    overwrite an existing shared file without inspecting it first.
    """

    max_messages: int
    messages_sent: int = 0
    read_files: set[str] = field(default_factory=set)


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "send_message",
            "description": "Send one short coordination message to the hub chat. Do not paste code here.",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "Short coordination message. No full code blocks.",
                    },
                },
                "required": ["content"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "upload_file",
            "description": "Upload code or documentation to the shared file store.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "Shared file name to create or update.",
                    },
                    "content": {
                        "type": "string",
                        "description": "Full file content to upload.",
                    },
                },
                "required": ["filename", "content"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a shared file by name before reviewing or overwriting it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "Shared file name to read.",
                    },
                },
                "required": ["filename"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pass_turn",
            "description": "Use when there is no useful non-duplicative action to take.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "Short reason for staying silent.",
                    },
                },
                "required": ["reason"],
                "additionalProperties": False,
            },
        },
    },
]


def parse_tool_arguments(raw_arguments: str) -> dict:
    """
    Parse model tool-call arguments safely.
    """

    try:
        arguments = json.loads(raw_arguments or "{}")
    except json.JSONDecodeError:
        return {}

    if isinstance(arguments, dict):
        return arguments

    return {}


def _shared_file_exists(filename: str) -> bool:
    return any(get_file_name(file_info) == filename for file_info in list_files())


def _looks_secret_like(content: str) -> bool:
    upper_content = content.upper()
    return any(pattern.upper() in upper_content for pattern in BLOCKED_RESPONSE_PATTERNS)


def _send_message(arguments: dict, state: HubToolState) -> str:
    content = str(arguments.get("content", "")).strip()

    if not content:
        return "send_message skipped: empty content."

    if state.messages_sent >= state.max_messages:
        return "send_message skipped: max chat messages reached."

    if "```" in content:
        return "send_message rejected: upload code with upload_file instead of pasting it into chat."

    if len(content) > MAX_CHAT_MESSAGE_CHARS:
        return "send_message rejected: message is too long for coordination chat."

    safe_content = sanitize_hub_response(content)

    if HUB_DRY_RUN:
        state.messages_sent += 1
        return f"DRY RUN: would send chat message:\n{safe_content}"

    seq = post_chat_message(safe_content)
    state.messages_sent += 1
    return f"Sent chat message with seq={seq}."


def _read_file(arguments: dict, state: HubToolState) -> str:
    filename = str(arguments.get("filename", "")).strip()

    if not filename:
        return "read_file failed: missing filename."

    content = read_shared_file(filename)

    if content is None:
        return f"read_file failed: shared file not found: {filename}"

    state.read_files.add(filename)
    return f"Shared file: {filename}\n\n{content}"


def _upload_file(arguments: dict, state: HubToolState) -> str:
    filename = str(arguments.get("filename", "")).strip()
    content = arguments.get("content", "")

    if not filename:
        return "upload_file failed: missing filename."

    if not isinstance(content, str) or not content.strip():
        return "upload_file failed: missing file content."

    if _looks_secret_like(content):
        return "upload_file rejected: content appears to contain secret-related text."

    if _shared_file_exists(filename) and filename not in state.read_files:
        return (
            "upload_file rejected: shared file already exists. "
            "Use read_file on this filename before overwriting it."
        )

    if HUB_DRY_RUN:
        return f"DRY RUN: would upload shared file {filename} ({len(content)} chars)."

    result = upload_shared_file(filename, content)
    state.read_files.add(filename)
    return f"Uploaded shared file {filename}. Hub response: {result}"


def _pass_turn(arguments: dict, state: HubToolState) -> str:
    reason = str(arguments.get("reason", "No useful action.")).strip()
    return f"Passed turn: {reason}"


def execute_tool(name: str, arguments: dict, state: HubToolState) -> str:
    """
    Execute one model-selected hub tool.
    """

    if name == "send_message":
        return _send_message(arguments, state)

    if name == "upload_file":
        return _upload_file(arguments, state)

    if name == "read_file":
        return _read_file(arguments, state)

    if name == "pass_turn":
        return _pass_turn(arguments, state)

    return f"Unknown tool: {name}"
