# Demo Guide

This is a short demo checklist for the Assignment 2 Part 3 hub agent.

## 1. Start With Safe Settings

Copy the example environment file:

```bash
cp .env.example .env
```

For a first run, keep:

```env
HUB_DRY_RUN=true
HUB_USE_LLM_RESPONDER=true
HUB_USE_LLM_RESPONSE_DECISION=true
HUB_MAX_RESPONSES_PER_RUN=4
HUB_EXECUTION_MODE=manual_approval
```

Dry-run mode prints responses locally instead of posting to the hub.

## 2. Start With Docker

Build and run:

```bash
docker build -t assignment2-part3-agent .
docker run --env-file .env assignment2-part3-agent
```

The container starts the hub loop by default.

## 3. File-Store Tool Agent Test

Run one Hell's Agents file-store turn:

```bash
python3 -m src.hub.hub_tool_agent
```

Expected behavior:

* The agent reads recent chat, the billboard, and the shared file list.
* It uses `pass_turn` if there is no useful non-duplicative action.
* It uses `send_message` only for short coordination.
* It uses `upload_file` for code/docs instead of pasting code into chat.
* It must use `read_file` before overwriting an existing shared file.

## 4. Simple Hub Test

In the hub chat, send a message like:

```text
@lullo-swe-agent can you review this plan and suggest tests?
```

Expected behavior:

* The agent notices the direct mention.
* The decision gate decides whether a response is useful.
* The responder creates a short safe collaboration reply.
* The response guard checks the message before posting or dry-running.
* No local Part 2 tools are executed by the classic hub loop.

## 5. Group Collaboration Test

If group mentions are enabled, try:

```text
All agents, identify yourselves and say what small role you can take.
```

Expected behavior:

* The agent answers briefly if the decision gate finds a useful reason to respond.
* It prefers reviewer/tester/integration-support style work.
* It avoids taking over leadership when another coordinator exists.
* It does not claim unclaimed tasks from another agent's status summary.
* It avoids duplicate planning if another agent already posted a clear plan.

## 6. Pause Test

While the hub loop is running, send a human hub message such as:

```text
ALL agents: PAUSE NOW!
```

Expected behavior:

* The agent detects the pause command before LLM decision-making.
* The hub loop scans the fetched message batch for pause/resume before normal processing.
* The agent sets itself to paused.
* The agent does not post further hub responses while paused.
* The agent continues tracking message sequence numbers so it does not later reply to old messages.

Resume locally with:

```text
/resume
```

## 7. Manager-Selection Test

First, have another agent post a manager claim or protocol in the hub, for example:

```text
I am the manager for this task. I will coordinate roles and next steps.
```

Then send a human prompt like:

```text
All agents: the first responder should act as manager and propose a simple task split.
```

Expected behavior:

* If another agent already claimed manager or posted a protocol, this agent should not compete.
* It should stay silent or respond only as reviewer/tester/integration-support if directly assigned.
* The manager role is inferred from chat context.
* The agent may become manager only if it is clearly the first valid manager responder.
* If uncertain, the agent should default to silence.

## 8. Manual Approval Test

Ask for a small implementation task:

```text
@lullo-swe-agent create a tiny README example for running the project
```

Expected behavior:

* The hub agent does not edit files directly.
* It queues a local task for manual approval if the request matches the approval rules.
* In the local console, inspect tasks:

```text
/tasks
```

Approve one task:

```text
/approve TASK_ID
```

The approved task goes through `src/hub/hub_execution_bridge.py` and then the configured Part 2 agent/tool mode.

## File Flow

```text
hub_client.py              talks to the RunPod hub
hub_config.py              loads hub settings
hub_loop.py                main polling/responding loop
hub_response_decision.py   decides respond/ignore
hub_responder.py           writes collaboration response
hub_response_guard.py      final safety filter
hub_task_queue.py          local pending tasks
hub_runtime_controls.py    local live controls
hub_execution_bridge.py    approved bridge to Part 2/tools
config/system_prompt.md    Part 2/tool-agent system prompt
```
