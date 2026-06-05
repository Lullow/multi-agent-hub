import os
from dotenv import load_dotenv


# Load local environment variables from .env during development.
# In production, these values can instead come from the runtime environment.
load_dotenv()

# When enabled, the hub loop prints planned responses instead of posting them.
HUB_DRY_RUN = os.getenv("HUB_DRY_RUN", "true").lower() == "true"

# Safety cap for how many hub messages the agent may answer in one run.
HUB_MAX_RESPONSES_PER_RUN = int(os.getenv("HUB_MAX_RESPONSES_PER_RUN", "3"))

# Safety cap for the file-store tool agent. The server allows 10 chat messages,
# but the default stays low for testing.
HUB_TOOL_MAX_MESSAGES = int(os.getenv("HUB_TOOL_MAX_MESSAGES", "3"))

# Token cap for the file-store tool agent so OpenRouter does not default
# to a very large completion budget.
HUB_TOOL_MAX_TOKENS = int(os.getenv("HUB_TOOL_MAX_TOKENS", "1200"))

# Remove trailing slash so endpoint paths can be joined consistently.
HUB_BASE_URL = os.getenv("HUB_BASE_URL", "").rstrip("/")

# Secrets should be read from environment variables, never hardcoded.
HUB_PASSWORD = os.getenv("HUB_PASSWORD", "")

# Default agent name used when no custom name is provided.
HUB_AGENT_NAME = os.getenv("HUB_AGENT_NAME", "lullo-swe-agent")

# How often the agent polls the hub for new tasks.
HUB_POLL_INTERVAL_SECONDS = float(os.getenv("HUB_POLL_INTERVAL_SECONDS", "1.2"))

# Controls how far the hub agent is allowed to go when handling task-like messages.
# Default is review_only so the agent gives feedback/suggestions instead of executing work.
HUB_EXECUTION_MODE = os.getenv("HUB_EXECUTION_MODE", "review_only").strip().lower()

# Controls what happens after a hub task receives explicit local approval.
HUB_APPROVED_TASK_RUNNER = os.getenv("HUB_APPROVED_TASK_RUNNER", "placeholder").strip().lower()


# Safety switch: keep LLM responses disabled by default until explicitly enabled.
HUB_USE_LLM_RESPONDER = os.getenv("HUB_USE_LLM_RESPONDER", "false").strip().lower() == "true"

# Optional LLM-based decision gate for deciding whether a hub message deserves a response.
# This helps the agent behave more flexibly in unpredictable multi-agent chats.
HUB_USE_LLM_RESPONSE_DECISION = (
    os.getenv("HUB_USE_LLM_RESPONSE_DECISION", "false").strip().lower() == "true"
)

# Small token cap because the decision gate should only return a tiny JSON decision.
HUB_DECISION_MAX_TOKENS = int(os.getenv("HUB_DECISION_MAX_TOKENS", "120"))

# Token cap for hub responses to avoid overly long replies and unnecessary cost.
HUB_RESPONDER_MAX_TOKENS = int(os.getenv("HUB_RESPONDER_MAX_TOKENS", "200"))

HUB_APPROVED_TASK_TOOL_MODE = os.getenv("HUB_APPROVED_TASK_TOOL_MODE","read_only").strip().lower()

HUB_ENABLE_GROUP_MENTIONS = (os.getenv("HUB_ENABLE_GROUP_MENTIONS", "false").strip().lower() == "true")


def validate_hub_config() -> None:
    """
    Validate required hub configuration.

    The real hub password should be stored in .env, never hardcoded in source code.
    """

    allowed_execution_modes = {"review_only", "manual_approval"}
    allowed_task_runners = {"placeholder", "part2_agent"}
    allowed_tool_modes = {"read_only", "local_tools"}

    if HUB_APPROVED_TASK_TOOL_MODE not in allowed_tool_modes:
        raise ValueError(
            "HUB_APPROVED_TASK_TOOL_MODE must be one of: "
            f"{', '.join(sorted(allowed_tool_modes))}"
    )

    if HUB_EXECUTION_MODE not in allowed_execution_modes:
        raise ValueError(
            "HUB_EXECUTION_MODE must be one of: "
            f"{', '.join(sorted(allowed_execution_modes))}"
        )

    if HUB_APPROVED_TASK_RUNNER not in allowed_task_runners:
        raise ValueError(
            "HUB_APPROVED_TASK_RUNNER must be one of: "
            f"{', '.join(sorted(allowed_task_runners))}"
        )

    if not HUB_BASE_URL:
        raise ValueError("Missing HUB_BASE_URL in environment.")

    if not HUB_PASSWORD:
        raise ValueError("Missing HUB_PASSWORD in environment.")

    if not HUB_AGENT_NAME:
        raise ValueError("Missing HUB_AGENT_NAME in environment.")

    if HUB_POLL_INTERVAL_SECONDS < 1.0:
        raise ValueError("HUB_POLL_INTERVAL_SECONDS must be at least 1.0 due to hub rate limit.")

    if HUB_RESPONDER_MAX_TOKENS <= 0:
        raise ValueError("HUB_RESPONDER_MAX_TOKENS must be greater than 0.")

    if HUB_DECISION_MAX_TOKENS <= 0:
        raise ValueError("HUB_DECISION_MAX_TOKENS must be greater than 0.")

    if HUB_TOOL_MAX_MESSAGES < 0 or HUB_TOOL_MAX_MESSAGES > 10:
        raise ValueError("HUB_TOOL_MAX_MESSAGES must be between 0 and 10.")

    if HUB_TOOL_MAX_TOKENS <= 0:
        raise ValueError("HUB_TOOL_MAX_TOKENS must be greater than 0.")
