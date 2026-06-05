import json
from dataclasses import dataclass

from src.hub.hub_config import (
    HUB_AGENT_NAME,
    HUB_DECISION_MAX_TOKENS,
    HUB_USE_LLM_RESPONSE_DECISION,
)
from src.hub.hub_responder import create_hub_llm_client, get_hub_model_name


@dataclass
class HubResponseDecision:
    """
    Decision object for whether the hub agent should respond.

    This is intentionally small:
    - should_respond controls whether the hub loop continues.
    - reason is logged locally for debugging.
    - response_type helps the responder understand what kind of value to provide.
    """

    should_respond: bool
    reason: str
    response_type: str


DEFAULT_NO_RESPONSE = HubResponseDecision(
    should_respond=False,
    reason="No clear useful contribution detected.",
    response_type="ignore",
)


DECISION_SYSTEM_PROMPT = """
You are a response decision gate for a software engineering collaboration agent.

Your job is NOT to answer the message.
Your job is only to decide whether this agent should respond in the shared group chat.

Core principle:
Default behavior is silence.

This is a large multi-agent group chat. Many agents may see the same message at the same time.
The agent should only respond when it has a clear, useful, non-duplicative reason to do so.

The agent's default role:
- safety-aware reviewer
- tester
- integration-support agent
- disciplined team-player

The agent is NOT normally:
- manager
- solo programmer
- main implementer
- planner
- CLI owner
- README owner
- task owner

Manager selection rules:
- If a human says the first answering agent becomes manager, only respond if this agent can reasonably be first.
- If another agent has already claimed manager, posted a protocol, or started manager-like coordination, choose ignore.
- If uncertain whether this agent is first, choose ignore.
- If this agent does become manager, response_type should be structure_project.
- If this agent is not manager, wait for direct assignment from the human or confirmed manager.

Roster rules:
- If a human or confirmed manager explicitly asks all agents for one roster line, choose answer_question.
- The response should be one short roster line only.
- Do not add extra protocol, planning, or task claims to roster replies.

Unclaimed task rules:
- If another agent lists remaining unclaimed tasks, choose ignore unless this agent is directly mentioned by name, or a human/confirmed manager explicitly assigns this agent a task.
- Do not claim CLI, README, implementation, planner, manager, or ownership roles from another agent's status summary.
- Do not claim work just because it matches this agent's default role.

Integration blocker exception:
- Default behavior is still silence.
- Ignore normal claims, status messages, and code dumps not directed at this agent.
- However, even without direct mention, choose integration_support for a clear unresolved integration blocker.
- Examples:
  - ModuleNotFoundError
  - failing tests
  - import path mismatch
  - API drift between modules
  - conflicting canonical file names
  - missing required method or attribute
  - code that contradicts the manager's locked API
  - unsafe eval usage if no one has already addressed it- Only respond if the blocker appears unresolved or not already clearly handled by the manager or another agent.

- Keep the response short and focused on the blocker.
- Do not claim ownership of the task unless directly assigned.

Project status and completion questions:
- If a human or all-agents message asks for project status, results, who did what, or how to test, choose answer_question.
- Base the answer on visible hub evidence such as claims, done reports, posted code, test results, and manager summaries.
- Do not answer if the message is only another agent's completion/status report and not a human/all-agents question.

Respond when:
- the message directly mentions this agent by full name
- a human directly assigns this agent a task
- a confirmed manager directly assigns this agent a task
- this agent is explicitly asked for review, tests, integration feedback, or clarification
- a human/manager asks all agents for exactly one roster line
- this agent owns an active task and has concrete output or a concrete blocker

Usually ignore:
- online/status/readiness messages
- acknowledgements
- "I will..." messages
- another agent claiming work
- another agent posting a plan
- another agent listing open tasks
- another agent posting code without asking this agent for review
- manager debates not directed at this agent
- role proposals not directed at this agent
- project completion messages unless directly asked
- vague "available to help" messages
- human messages directed at another named agent

Code/review rules:
- If substantial code is posted and this agent is directly asked to review it, choose review_feedback.
- If substantial code is posted but nobody asks this agent for review, choose ignore unless there is an obvious critical integration or safety issue.
- If there is a visible API/schema/import mismatch and this agent is expected to provide integration support, choose integration_support.
- If code is incomplete or unstable, prefer integration_support or review_feedback over test_plan.

Pause/stop:
- If a human says stop, pause, or stop talking, choose ignore. Runtime code handles pausing separately.

Important:
- The shared chat is the only common knowledge source.
- If the agent responds later, it must provide visible output.
- Do not mark something as done unless the result is included in the chat.
- Prefer missing a possible response over creating spam or duplicate work.

Output format rules:
- Keep "reason" under 12 words.
- Return compact JSON only.
- Do not include markdown fences.
- Do not include extra explanation.

Return JSON only with exactly these fields:
{
    "should_respond": true or false,
    "reason": "short reason",
    "response_type": "one of: structure_project, claim_review_task, review_feedback, test_plan, integration_support, code_suggestion, clarify, answer_question, ignore"
}
""".strip()


def _extract_json_object(raw_text: str) -> str:
    """
    Extract a JSON object from model output.

    Some models wrap JSON in markdown fences or add short explanations.
    This keeps the decision gate robust while still requiring a valid JSON object.
    """

    cleaned = raw_text.strip()

    if cleaned.startswith("```json"):
        cleaned = cleaned.removeprefix("```json").strip()

    if cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```").strip()

    if cleaned.endswith("```"):
        cleaned = cleaned.removesuffix("```").strip()

    start = cleaned.find("{")
    end = cleaned.rfind("}")

    if start == -1 or end == -1 or end <= start:
        return cleaned

    return cleaned[start : end + 1]


def _parse_decision_json(raw_text: str) -> HubResponseDecision:
    """
    Parse the LLM decision safely.

    If parsing fails or required fields are missing, default to no response.
    This prevents malformed model output from causing hub spam.
    """

    json_text = _extract_json_object(raw_text)

    try:
        data = json.loads(json_text)
    except json.JSONDecodeError:
        return HubResponseDecision(
            should_respond=False,
            reason="Decision JSON parse failed.",
            response_type="ignore",
        )

    should_respond = data.get("should_respond")
    reason = data.get("reason", "")
    response_type = data.get("response_type", "ignore")

    if not isinstance(should_respond, bool):
        return DEFAULT_NO_RESPONSE

    if not isinstance(reason, str):
        reason = "No valid reason provided."

    if not isinstance(response_type, str):
        response_type = "ignore"

    allowed_response_types = {
        "structure_project",
        "claim_review_task",
        "review_feedback",
        "test_plan",
        "integration_support",
        "code_suggestion",
        "clarify",
        "answer_question",
        "ignore",
    }

    if response_type not in allowed_response_types:
        response_type = "ignore"

    return HubResponseDecision(
        should_respond=should_respond,
        reason=reason.strip() or "No reason provided.",
        response_type=response_type,
    )


def decide_hub_response(
    message: dict,
    intent: str | None = None,
    is_group_context: bool = False,
) -> HubResponseDecision:
    """
    Decide whether this agent should respond to a hub message.

    Hard safety checks should happen before this function in hub_loop.py.
    This function only handles collaboration relevance.
    It does not post, execute tools, or approve local work.

    If HUB_USE_LLM_RESPONSE_DECISION is disabled, the function falls back to
    direct mentions and group/task-like intent handling.
    """

    sender = message.get("agent_name", "unknown-agent")
    content = message.get("content", "")

    if not HUB_USE_LLM_RESPONSE_DECISION:
        normalized = content.lower()
        agent_name = HUB_AGENT_NAME.lower()

        if f"@{agent_name}" in normalized:
            return HubResponseDecision(
                should_respond=True,
                reason="Direct mention detected.",
                response_type="answer_question",
            )

        if is_group_context:
            return HubResponseDecision(
                should_respond=True,
                reason="Group collaboration mention detected.",
                response_type="structure_project",
            )

        return DEFAULT_NO_RESPONSE

    client = create_hub_llm_client()
    model_name = get_hub_model_name()

    user_prompt = f"""
Agent name: {HUB_AGENT_NAME}
Sender: {sender}
Detected keyword intent hint: {intent or "unknown"}

Hub message:
{content}

Decide if the agent should respond.
Return JSON only.
""".strip()

    completion = client.chat.completions.create(
        model=model_name,
        messages=[
            {
                "role": "system",
                "content": DECISION_SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": user_prompt,
            },
        ],
        max_tokens=HUB_DECISION_MAX_TOKENS,
        temperature=0,
    )

    raw_answer = completion.choices[0].message.content

    if not raw_answer:
        return DEFAULT_NO_RESPONSE

    print("Raw decision response:")
    print(raw_answer)

    return _parse_decision_json(raw_answer.strip())
