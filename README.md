# Assignment 2 Part 3 Hub Agent

This project is a Python hub agent for Assignment 2 Part 3. It connects to a shared RunPod hub, reads group-chat messages from other agents, decides whether it should respond, and posts safe collaboration replies.

The project builds on my Part 2 local SWE-agent, but the hub layer is intentionally separate. Hub messages are treated as untrusted input. They must not directly run bash, edit files, apply patches, or start the local Part 2 agent.

## What The Agent Does

* Connects to the shared RunPod/HTTP hub.
* Fetches only new messages.
* Uses a response decision gate to decide whether to respond or ignore.
* Generates short, safe collaboration replies.
* Runs every response through a final guard before posting.
* Avoids spam, duplicate work, and taking over other agents' tasks.
* Can queue direct implementation requests for local manual approval.
* Can optionally run a Hell's Agents file-store tool-use turn.

## Collaboration Behavior

The hub agent is designed to be a disciplined team-player in a large multi-agent group chat.

Its default behavior is silence. It should only respond when it has a clear, useful, non-duplicative contribution.

The agent normally acts as:

* safety-aware reviewer
* tester
* integration-support agent

It should not normally act as:

* solo programmer
* main implementer
* CLI owner
* README owner
* planner
* manager

The manager role is inferred from chat context. The agent may become manager only if a human prompt asks for a first-responder manager and this agent is clearly the first valid manager responder.

If another agent already posted a manager claim or protocol, this agent should stand down and behave as a worker/reviewer instead.

The responder should keep hub replies short, concrete, and focused. It should avoid multi-file dumps, generic acknowledgements, duplicate planning, and broad volunteering.

## Main Hub Flow

```text
RunPod hub message batch
-> src/hub/hub_loop.py fetches new messages
-> batch-level pause/resume scan before normal processing
-> manager-selection safety check
-> src/hub/hub_response_decision.py decides respond vs ignore
-> src/hub/hub_responder.py writes a short collaboration response
-> src/hub/hub_response_guard.py sanitizes the response
-> src/hub/hub_client.py posts the response
```

The Python code stays in control of polling, rate limits, response caps, dry-run mode, pause mode, sanitization, posting, and local approval.

Human pause/stop commands are handled in Python before any LLM decision or responder call. The hub loop scans each fetched message batch for pause/resume control messages before processing normal hub messages.

## Manual Approval Flow

Direct implementation-style hub requests can be queued locally, but they are not executed automatically.

```text
direct implementation request
-> local task queue
-> /tasks
-> /approve TASK_ID
-> src/hub/hub_execution_bridge.py
-> Part 2 agent/tools
```

This keeps remote hub input separated from local tool execution.

## Anti-Spam And Coordination Safety

To reduce noise in a large multi-agent chat, the agent follows these rules:

* Default to silence unless a response adds visible value.
* Do not claim unclaimed tasks from another agent's status summary.
* Do not compete if another agent already posted a manager claim or coordination protocol.
* Do not repeat plans, task breakdowns, or role assignments already posted by others.
* Keep replies short and concrete.
* Avoid dumping multiple full files into the hub chat.
* Respect response caps, pause mode, and dry-run mode.
* Require manual approval before any local tool execution.

## Important Files

| File                               | Purpose                                      |
| ---------------------------------- | -------------------------------------------- |
| `src/hub/hub_client.py`            | Talks to the RunPod hub API                  |
| `src/hub/hub_config.py`            | Loads and validates hub settings             |
| `src/hub/hub_loop.py`              | Main polling/responding loop                 |
| `src/hub/hub_response_decision.py` | Decides respond vs ignore                    |
| `src/hub/hub_responder.py`         | Writes safe collaboration responses          |
| `src/hub/hub_response_guard.py`    | Final safety filter before posting           |
| `src/hub/hub_file_client.py`       | Talks to hub messages, files, and billboard  |
| `src/hub/hub_tools.py`             | Implements LLM tools for the file-store flow |
| `src/hub/hub_tool_agent.py`        | Tool-use entry point for Hell's Agents       |
| `src/hub/hub_task_queue.py`        | Stores pending local approval tasks          |
| `src/hub/hub_runtime_controls.py`  | Handles local live control commands          |
| `src/hub/hub_execution_bridge.py`  | Approved bridge to Part 2/tools              |
| `config/system_prompt.md`          | System prompt for the Part 2/tool-agent flow |

`config/system_prompt.md` is not the main prompt for normal hub chat replies. Normal hub chat behavior is mainly controlled by `src/hub/hub_response_decision.py` and `src/hub/hub_responder.py`.

## Setup

Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create a local environment file:

```bash
cp .env.example .env
```

The code uses OpenAI-compatible API clients. I tested with OpenRouter and:

```env
MODEL_NAME=anthropic/claude-sonnet-4.6
```

GPT-4o can also be used as a fallback with an OpenAI-compatible configuration.

## Hub Configuration

Important `.env` values:

```env
OPENAI_API_KEY=your_openrouter_or_openai_key
OPENAI_BASE_URL=https://openrouter.ai/api/v1
MODEL_NAME=anthropic/claude-sonnet-4.6

HUB_AGENT_NAME=lullo-swe-agent
HUB_BASE_URL=https://your-runpod-hub-url
HUB_PASSWORD=your-hub-password

HUB_DRY_RUN=true
HUB_USE_LLM_RESPONDER=true
HUB_USE_LLM_RESPONSE_DECISION=true
HUB_MAX_RESPONSES_PER_RUN=4
HUB_TOOL_MAX_MESSAGES=3
HUB_POLL_INTERVAL_SECONDS=5
HUB_DECISION_MAX_TOKENS=200
HUB_RESPONDER_MAX_TOKENS=500

HUB_EXECUTION_MODE=manual_approval
HUB_APPROVED_TASK_RUNNER=part2_agent
HUB_APPROVED_TASK_TOOL_MODE=local_tools
```

Use `HUB_DRY_RUN=true` for the first demo so the agent prints what it would post without sending messages to the hub.

For stress testing, `HUB_MAX_RESPONSES_PER_RUN` can be raised temporarily, but a lower value is safer for live multi-agent collaboration.

## Run The Hub Agent

Local run:

```bash
python -m src.hub.hub_loop
```

or, if `python` is not available:

```bash
python3 -m src.hub.hub_loop
```

Docker:

```bash
docker build -t assignment2-part3-agent .
docker run --env-file .env assignment2-part3-agent
```

## Run The File-Store Tool Agent

The Hell's Agents file-store mode is a separate entry point:

```bash
python3 -m src.hub.hub_tool_agent
```

This mode reads the chat, billboard, and shared file list before acting. The LLM can choose one of four tools:

* `send_message`: short coordination only
* `upload_file`: upload code or docs to the shared file store
* `read_file`: inspect a shared file before review or overwrite
* `pass_turn`: stay silent when there is no useful action

Code should be shared through `upload_file`, not pasted into chat. Existing shared files must be read with `read_file` before they can be overwritten. `HUB_TOOL_MAX_MESSAGES=3` keeps testing safely below the server limit of 10 chat messages per agent.

## Runtime Controls

While the hub loop is running, type these commands in the local console:

| Command            | Effect                                     |
| ------------------ | ------------------------------------------ |
| `/status`          | Show pause state and response/token limits |
| `/pause`           | Keep polling but stop posting              |
| `/resume`          | Allow posting again                        |
| `/tokens N`        | Set response token limit                   |
| `/responses N`     | Set max responses for this run             |
| `/tasks`           | List pending local approval tasks          |
| `/approve TASK_ID` | Approve a queued task                      |
| `/reject TASK_ID`  | Reject a queued task                       |
| `/quit`            | Stop the hub loop                          |

## Safety Design

Hub messages are untrusted. The hub layer does not directly expose tools.

Safety decisions:

* No direct bash execution from hub messages.
* No direct file edits from hub messages.
* No automatic patch application from other agents.
* Manual approval is required before local tool execution.
* A response guard runs before anything is posted.
* Response caps and pause mode help avoid spam.
* Secrets and `.env` values must never be shared.
* Human pause/stop commands are handled in Python before LLM calls.

## Local Part 2 Tools

The Part 2 agent can use controlled tools after local approval, depending on configuration:

* `bash`
* `read_file`
* `edit_file_section`

These tools still pass through Part 2 safety checks such as command blocking, path safety, output limiting, and max step limits.

## Demo

See `DEMO.md` for a short walkthrough with Docker commands, hub test prompts, pause/manager tests, expected behavior, and manual approval testing.

## Known Limitations

* The agent does not have full persistent memory of the entire hub.
* Multi-agent behavior is unpredictable because other agents may behave differently.
* Manager race conditions can still happen in distributed chat.
* Behavior depends on model quality and hub timing.
* Tool execution results are local after approval unless manually shared back to the hub.
* The response decision and responder prompts can still be tuned further.
* The agent is not perfect; it may still miss context or respond too often if limits are set too high.
