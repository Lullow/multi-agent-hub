import time

from requests import RequestException

from src.hub.hub_client import fetch_messages, post_message
from src.hub.hub_config import (
    HUB_AGENT_NAME,
    HUB_DRY_RUN,
    HUB_MAX_RESPONSES_PER_RUN,
    HUB_POLL_INTERVAL_SECONDS,
    HUB_USE_LLM_RESPONDER,
    HUB_RESPONDER_MAX_TOKENS,
    HUB_EXECUTION_MODE,
    HUB_APPROVED_TASK_RUNNER,
    HUB_APPROVED_TASK_TOOL_MODE,
    HUB_ENABLE_GROUP_MENTIONS,
    validate_hub_config,
)
from src.hub.hub_intent import detect_hub_intent
from src.hub.hub_response_decision import decide_hub_response
from src.hub.hub_responder import build_llm_collaboration_response
from src.hub.hub_response_guard import sanitize_hub_response
from src.hub.hub_task_queue import HubTaskQueue
from src.hub.hub_runtime_controls import (
    HubRuntimeControls,
    start_console_control_thread,
)


GROUP_MENTION_KEYWORDS = [
    "@all",
    "@agents",
    "@bots",
    "@all-agents",
    "@all-bots",
    "@alla",
    "@alla-bottar",
    "alla bottar",
    "alla agenter",
    "all agents",
    "all bots",
]

IMPLEMENTATION_KEYWORDS = [
    "write",
    "create",
    "fix",
    "implement",
    "build",
    "add",
    "make",
    "generate",
    "skriv",
    "skapa",
    "fixa",
    "implementera",
    "bygg",
    "lägg till",
]

FILE_HINTS = [
    ".py",
    ".js",
    ".html",
    ".css",
    ".md",
    ".txt",
    ".json",
    ".yml",
    ".yaml",
    "file",
    "module",
    "endpoint",
    "test",
    "tests",
    "backend",
    "frontend",
]

# Hard runtime stop commands.
# These are handled before the LLM decision gate.
STOP_COMMAND_PHRASES = [
    "/stop",
    "/pause",
    "pause now",
    "all agents: pause now",
    "all agents pause",
    "everyone pause",
    "stop talking",
    "shut up",
    "stop posting",
    "everyone stop posting",
    "all agents stop",
    "stop now",
    "sluta prata",
    "sluta skriva",
    "pausa nu",
]

# Remote resume commands.
# Prefer exact slash commands to avoid accidental resume from normal project text.
RESUME_COMMANDS = {
    "/resume",
    "/continue",
    "/start",
}


def is_human_sender(message: dict) -> bool:
    """
    Treat human/user messages as operator-level control messages.

    Agent messages should not be able to pause or resume this agent.
    """

    sender = message.get("agent_name", "").lower()
    return sender in {"human", "user", "lullo"}


def is_stop_command(message: dict) -> bool:
    """
    Detect operator stop messages before the LLM decision gate.

    This is a hard runtime control, not a normal chat response.
    """

    if not is_human_sender(message):
        return False

    content = message.get("content", "").lower()
    return any(phrase in content for phrase in STOP_COMMAND_PHRASES)


def is_resume_command(message: dict) -> bool:
    """
    Detect operator resume messages before the LLM decision gate.

    Resume commands are exact commands to avoid accidental unpausing.
    """

    if not is_human_sender(message):
        return False

    content = message.get("content", "").strip().lower()
    return content in RESUME_COMMANDS


MANAGER_SELECTION_HINTS = [
    "first one that answers",
    "first one that responds",
    "first agent to respond",
    "first one that answers to this message",
    "first one that answers to this",
    "first one that responds to this message",
    "single agent acting as the head",
    "head of this agentic swe department",
    "manager in this session",
]

MANAGER_RESPONSE_HINTS = [
    "manager claim",
    "i am the manager",
    "i am the designated manager",
    "assume the role of manager",
    "acting as manager",
    "communication protocol",
    "work protocol",
    "swe hub communication protocol",
    "i will establish the communication",
    "do not start working",
    "roster",
    "[roster]",
]


def is_manager_selection_message(message: dict) -> bool:
    """
    Detect human messages that ask the first responder to become manager.
    """

    if not is_human_sender(message):
        return False

    content = message.get("content", "").lower()
    return any(hint in content for hint in MANAGER_SELECTION_HINTS)


def looks_like_manager_response(message: dict) -> bool:
    """
    Detect whether another agent already responded like a manager.

    This is intentionally conservative. If another agent already posted a
    manager claim or full protocol, this agent should not compete.
    """

    sender = message.get("agent_name", "")

    if sender == HUB_AGENT_NAME:
        return False

    if is_human_sender(message):
        return False

    content = message.get("content", "").lower()
    return any(hint in content for hint in MANAGER_RESPONSE_HINTS)


def batch_has_later_manager_response(messages: list[dict], manager_prompt_seq: int | None) -> bool:
    """
    Check whether a later message in the same batch already looks like a manager response.

    This prevents the agent from claiming manager after another agent already
    responded to the same manager-selection prompt.
    """

    if manager_prompt_seq is None:
        return False

    for message in messages:
        seq = get_message_seq(message)

        if seq is None or seq <= manager_prompt_seq:
            continue

        if looks_like_manager_response(message):
            return True

    return False


def is_direct_mention_for_agent(content: str) -> bool:
    """
    Check whether the message directly addresses this agent.

    This is intentionally stricter than group mentions. It is used only for
    deciding whether a task may be queued for local manual approval.
    """

    normalized_content = content.lower()
    normalized_agent_name = HUB_AGENT_NAME.lower()

    return (
        f"@{normalized_agent_name}" in normalized_content
        or normalized_agent_name in normalized_content
    )


def looks_like_implementation_request(content: str) -> bool:
    """
    Check whether a message asks for concrete implementation work.

    This is only a heuristic. It does not execute anything by itself.
    The task still requires local manual approval before tools can run.
    """

    normalized = content.lower()

    has_action = any(keyword in normalized for keyword in IMPLEMENTATION_KEYWORDS)
    has_file_or_code_hint = any(hint in normalized for hint in FILE_HINTS)

    return has_action and has_file_or_code_hint


def should_queue_for_manual_approval(message: dict, response_type: str | None) -> bool:
    """
    Decide whether a hub message should become a local approval task.

    This is the only path from a hub request into the local task queue.
    The queued task still requires a local `/approve TASK_ID` command.

    Rules:
    - only direct messages to this agent
    - only concrete implementation-like requests
    - only when the decision gate already chose to respond
    - never broad group kickoff messages
    """

    content = message.get("content", "")

    if not is_direct_mention_for_agent(content):
        return False

    if is_group_mention(content):
        return False

    if response_type not in {"claim_review_task", "code_suggestion", "integration_support"}:
        return False

    return looks_like_implementation_request(content)


def get_message_seq(message: dict) -> int | None:
    """
    Extract message sequence number safely.

    The hub should return seq as an integer, but this also handles
    numeric strings defensively.
    """

    seq = message.get("seq")

    if isinstance(seq, int):
        return seq

    if isinstance(seq, str) and seq.isdigit():
        return int(seq)

    return None


def build_simple_response(message: dict) -> str:
    """
    Build a safe minimal response.

    This version does not call the SWE-agent or any tools.
    """

    sender = message.get("agent_name", "unknown-agent")

    return (
        f"Hi {sender}, this is {HUB_AGENT_NAME}. "
        "I received your message. I am currently running in safe hub mode, "
        "so I can acknowledge relevant hub messages but I am not executing code "
        "or editing files automatically."
    )


def build_response(
    message: dict,
    intent: str | None = None,
    max_tokens: int | None = None,
    response_type: str | None = None,
    decision_reason: str | None = None,
) -> str:
    """
    Build a response for a hub message.

    By default, this uses the simple safe response.
    If HUB_USE_LLM_RESPONDER is enabled, it tries to use the LLM-based responder.

    If the LLM responder fails, the agent falls back to the simple safe response
    instead of crashing the hub loop.
    """

    if HUB_USE_LLM_RESPONDER:
        try:
            return build_llm_collaboration_response(
                message,
                intent=intent,
                max_tokens=max_tokens,
                response_type=response_type,
                decision_reason=decision_reason,
            )
        except Exception as error:
            print(f"LLM responder failed, falling back to simple response: {error}")
            return build_simple_response(message)

    return build_simple_response(message)


def is_group_mention(content: str) -> bool:
    """
    Check whether a message appears to address all agents/bots.

    Group mentions are optional because responding to broad messages can create
    coordination noise if every agent replies at once.
    """

    normalized = content.lower()

    return any(keyword in normalized for keyword in GROUP_MENTION_KEYWORDS)


def run_hub_loop() -> None:
    """
    Run the hub polling loop.

    The loop uses a simple architecture:
    1. Fetch new hub messages.
    2. Apply hard Python safety checks.
    3. Use keyword intent only as a lightweight hint.
    4. Use the LLM decision gate to decide whether to respond.
    5. Generate a safe text-only response.
    6. Sanitize before printing or posting.

    Operator stop/resume commands are handled before the LLM decision gate.
    """

    validate_hub_config()

    controls = HubRuntimeControls(
        paused=False,
        should_stop=False,
        max_responses_per_run=HUB_MAX_RESPONSES_PER_RUN,
        max_tokens=HUB_RESPONDER_MAX_TOKENS,
    )

    task_queue = HubTaskQueue()

    # Start local console controls in the background without blocking hub polling.
    start_console_control_thread(controls, task_queue=task_queue)

    responses_sent = 0
    last_seen = 0

    try:
        # Load existing messages once so the agent does not reply to old hub history.
        existing_messages = fetch_messages(since=0)

        for message in existing_messages:
            seq = get_message_seq(message)

            if seq is not None:
                last_seen = max(last_seen, seq)

    except RequestException as error:
        print(f"Could not fetch existing hub messages at startup: {error}")
        print("Starting with last_seen = 0. The loop will retry.")

    print(f"Starting from latest existing seq: {last_seen}")
    print(f"Starting hub loop as: {HUB_AGENT_NAME}")
    print("Safe hub mode is enabled.")
    print(f"Dry run: {HUB_DRY_RUN}")
    print(f"Execution mode: {HUB_EXECUTION_MODE}")
    print(f"Approved task runner: {HUB_APPROVED_TASK_RUNNER}")
    print(f"LLM responder: {HUB_USE_LLM_RESPONDER}")
    print(f"Approved task tool mode: {HUB_APPROVED_TASK_TOOL_MODE}")
    print(f"Group mentions: {HUB_ENABLE_GROUP_MENTIONS}")
    print(f"Max responses per run: {controls.max_responses_per_run}")
    print(f"Max tokens: {controls.max_tokens}")
    print(f"Poll interval: {HUB_POLL_INTERVAL_SECONDS} seconds")
    print("Press Ctrl+C to stop.\n")

    try:
        while not controls.should_stop:
            try:
                # Fetch only messages newer than the latest sequence number we have seen.
                messages = fetch_messages(since=last_seen)

                # First pass: update last_seen and detect operator controls before any LLM calls.
                latest_control: str | None = None
                latest_control_seq = -1

                for message in messages:
                    seq = get_message_seq(message)

                    if seq is not None:
                        last_seen = max(last_seen, seq)

                    if seq is None:
                        continue

                    if is_stop_command(message) and seq > latest_control_seq:
                        latest_control = "pause"
                        latest_control_seq = seq

                    if is_resume_command(message) and seq > latest_control_seq:
                        latest_control = "resume"
                        latest_control_seq = seq

                if latest_control == "pause":
                    controls.paused = True
                    print("Human pause/stop command found in batch. Agent is now paused.")
                    continue

                if latest_control == "resume":
                    controls.paused = False
                    print("Human resume command found in batch. Agent is now resumed.")
                    continue

            except RequestException as error:
                print(f"Could not fetch hub messages: {error}")
                time.sleep(HUB_POLL_INTERVAL_SECONDS)
                continue

            for message in messages:
                seq = get_message_seq(message)

                # Update last_seen even for ignored messages so they are not processed again.
                if seq is not None:
                    last_seen = max(last_seen, seq)

                sender = message.get("agent_name", "unknown-agent")
                content = message.get("content", "")

                # Hard safety gate: never respond to ourselves or empty messages.
                if sender == HUB_AGENT_NAME:
                    continue

                if not content:
                    continue

                # Operator stop/resume is handled before any LLM calls.
                if is_stop_command(message):
                    controls.paused = True
                    print("Hub stop command received from human. Agent is now paused.")
                    continue

                if is_resume_command(message):
                    controls.paused = False
                    print("Hub resume command received from human. Agent is now resumed.")
                    continue

                # While paused, the agent still updates last_seen, but does not call the LLM
                # or post anything. This prevents delayed replies after a stop command.
                if controls.paused:
                    print(f"Agent is paused. Ignoring hub message from {sender}.")
                    continue

                # Manager-selection messages are risky in large multi-agent chats.
                # Only allow this agent to compete if no later message in the same
                # batch already looks like a manager claim or protocol response.
                if is_manager_selection_message(message):
                    manager_prompt_seq = get_message_seq(message)

                    if batch_has_later_manager_response(messages, manager_prompt_seq):
                        print(
                            "Manager selection already has a later manager-like response. "
                            "Ignoring to avoid duplicate managers."
                        )
                        continue

                mentions_group = HUB_ENABLE_GROUP_MENTIONS and is_group_mention(content)

                # Keyword intent is only a hint, not the final routing decision.
                intent = detect_hub_intent(content)

                decision = decide_hub_response(
                    message,
                    intent=intent,
                    is_group_context=mentions_group,
                )

                if not decision.should_respond:
                    print(f"Ignoring message from {sender}: {decision.reason}")
                    continue

                # Safety cap to avoid spamming the hub or using too many LLM calls.
                if responses_sent >= controls.max_responses_per_run:
                    print("Max responses reached for this run. Staying online but not posting more responses.")
                    continue

                print(f"Received relevant message from {sender}: {content}")
                print(f"Detected intent: {intent}")
                print(f"Decision: {decision.response_type} - {decision.reason}")

                if should_queue_for_manual_approval(message, decision.response_type):
                    queued_task = task_queue.add_task(
                        sender=sender,
                        content=content,
                        intent=intent,
                    )

                    response = (
                        f"[CLAIM]: I can take this task via local manual approval.\n"
                        f"[OUTPUT]: Queued locally as task #{queued_task.task_id}. "
                        f"I will only execute tools after local approval.\n"
                        f"[NEXT]: Use `/tasks` locally to inspect it, then "
                        f"`/approve {queued_task.task_id}` or `/reject {queued_task.task_id}`."
                    )
                else:
                    response = build_response(
                        message,
                        intent=intent,
                        max_tokens=controls.max_tokens,
                        response_type=decision.response_type,
                        decision_reason=decision.reason,
                    )

                # Final safety layer before anything is printed or posted to the shared hub.
                response = sanitize_hub_response(response, fallback_sender=sender)

                if controls.paused:
                    print("Agent paused before posting. Dropping generated response.")
                    continue

                if HUB_DRY_RUN:
                    responses_sent += 1
                    print("Dry run enabled. Would post response:")
                    print(response)
                    print(f"Dry-run responses this run: {responses_sent}/{controls.max_responses_per_run}")
                else:
                    try:
                        posted_seq = post_message(response)
                    except RequestException as error:
                        print(f"Could not post hub response: {error}")
                        time.sleep(HUB_POLL_INTERVAL_SECONDS)
                        continue

                    responses_sent += 1

                    print(f"Posted response with seq: {posted_seq}")
                    print(f"Responses sent this run: {responses_sent}/{controls.max_responses_per_run}")

                    # Extra sleep after posting because POST is also a request.
                    time.sleep(HUB_POLL_INTERVAL_SECONDS)

            # Sleep after every successful polling cycle.
            time.sleep(HUB_POLL_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        controls.should_stop = True
        print("\nHub loop stopped by user.")


if __name__ == "__main__":
    run_hub_loop()