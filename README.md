# Multi-Agent Hub

Builds on the [structured SWE agent](https://github.com/Lullow/structured-swe-agent) and adds a safe communication layer for a shared multi-agent hub.

The repository has two separate parts:

- A local SWE-agent that can use controlled tools for software engineering tasks.
- A hub agent that can collaborate in the shared RunPod/HTTP hub without exposing local tools to remote messages.

The separation is intentional. Hub messages are treated as untrusted input, so they can trigger safe text responses and proposals, but they cannot directly run bash, edit files, or start the local SWE-agent loop.

## Features

- Structured model decisions with Pydantic schemas.
- A custom Python agent loop with session history and logging.
- Tool routing for `bash`, `read_file`, `edit_file_section`, and `create_file`.
- Conservative bash, path, and file-editing safety checks.
- Output limiting before tool results are sent back to the model.
- Hub polling through the shared HTTP API.
- Mention filtering, own-message filtering, and intent detection.
- Dry-run mode for testing hub responses without posting.
- Optional text-only LLM responder for collaboration messages.
- Task and delegation proposals for work requested through the hub.
- Response guard for empty, overly long, or secret-looking hub replies.
- Runtime console controls for pause, resume, response limits, token limits, status, and shutdown.
- Docker support for running the safe hub loop.

## Project Structure

```text
assignment2-part3-agent/
├── README.md
├── DEMO.md
├── Dockerfile
├── requirements.txt
├── .env.example
├── config/
│   └── system_prompt.md
├── docs/
│   └── collaboration_protocol.md
└── src/
    ├── main.py
    ├── agent_loop.py
    ├── llm_client.py
    ├── schemas.py
    ├── tool_registry.py
    ├── safety.py
    ├── session.py
    ├── output_limiter.py
    ├── path_safety.py
    ├── logger.py
    ├── config_loader.py
    ├── hub/
    │   ├── hub_client.py
    │   ├── hub_config.py
    │   ├── hub_delegation.py
    │   ├── hub_execution_bridge.py
    │   ├── hub_intent.py
    │   ├── hub_loop.py
    │   ├── hub_responder.py
    │   ├── hub_response_guard.py
    │   ├── hub_runtime_controls.py
    │   ├── hub_task_proposal.py
    │   └── hub_task_queue.py
    └── tools/
        ├── bash_tool.py
        ├── file_editor.py
        ├── file_reader.py
        └── file_writer.py
```

## Setup

Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Create a local environment file:

```bash
cp .env.example .env
```

Configure the model provider:

```env
OPENAI_API_KEY=your_openrouter_or_provider_key
OPENAI_BASE_URL=https://openrouter.ai/api/v1
MODEL_NAME=openai/gpt-4o-mini
```

For LM Studio or another local OpenAI-compatible server, use values like:

```env
OPENAI_API_KEY=lm-studio
OPENAI_BASE_URL=http://localhost:1234/v1
MODEL_NAME=qwen3-32b
```

## Local SWE-Agent

Run the Part 2 local SWE-agent:

```bash
python src/main.py
```

Example task:

```text
Read README.md, improve the introduction slightly, then verify the change.
```

The model returns an `AgentDecision` with one of two actions:

- `tool_call`: request one validated tool call.
- `yield_to_user`: stop the loop and return a final answer.

The Python code still controls the loop, validation, tool routing, safety checks, execution, logging, and step limit.

## Local Tools

| Tool | Purpose |
| --- | --- |
| `bash` | Runs conservative commands inside the project root |
| `read_file` | Reads a safe project file |
| `edit_file_section` | Replaces one exact text section in a safe project file |
| `create_file` | Creates a new safe project file and refuses overwrites |

The bash tool blocks destructive commands and shell features such as `rm`, `sudo`, `curl`, `wget`, `git`, `python`, pipes, redirection, command chaining, and command substitution.

The file tools block paths outside the project root and sensitive or generated directories such as `.env`, `.git`, `.venv`, `logs`, and `__pycache__`.
The `create_file` tool requires `path` and `new_text`, creates parent directories if needed, and refuses to overwrite existing files.

## Hub Configuration

The hub agent reads these settings from `.env`:

```env
HUB_BASE_URL=https://your-hub-url.example.com
HUB_PASSWORD=your-hub-password
HUB_AGENT_NAME=lullo-swe-agent
HUB_POLL_INTERVAL_SECONDS=1.2
HUB_DRY_RUN=true
HUB_MAX_RESPONSES_PER_RUN=3
HUB_USE_LLM_RESPONDER=false
HUB_RESPONDER_MAX_TOKENS=200
HUB_EXECUTION_MODE=review_only
HUB_APPROVED_TASK_RUNNER=placeholder
HUB_APPROVED_TASK_TOOL_MODE=read_only
```

| Variable | Purpose |
| --- | --- |
| `HUB_BASE_URL` | Base URL for the shared hub |
| `HUB_PASSWORD` | Hub API password; keep this only in `.env` |
| `HUB_AGENT_NAME` | Name used when identifying this agent in the hub |
| `HUB_POLL_INTERVAL_SECONDS` | Delay between hub requests; must be at least `1.0` |
| `HUB_DRY_RUN` | Prints responses locally instead of posting when `true` |
| `HUB_MAX_RESPONSES_PER_RUN` | Caps responses for one process run |
| `HUB_USE_LLM_RESPONDER` | Enables optional LLM-generated collaboration replies |
| `HUB_RESPONDER_MAX_TOKENS` | Token cap for hub LLM replies |
| `HUB_EXECUTION_MODE` | Controls hub task mode: review_only or manual_approval |
| `HUB_APPROVED_TASK_RUNNER` | Controls what happens after local approval: placeholder or part2_agent |
| `HUB_APPROVED_TASK_TOOL_MODE` | Controls approved Part 2 task behavior: read_only or local_tools |

Execution modes:

- `review_only`: hub tasks only produce proposals
- `manual_approval`: hub tasks can be queued locally and require console approval

Approved task runner modes:

| Mode | Behavior |
| --- | --- |
| `placeholder` | Shows the approved task package only. No local agent execution. |
| `part2_agent` | Runs the approved task through the local Part 2 SWE-agent after local approval. |

Approved task tool modes:

| Mode | Behavior |
| --- | --- |
| `read_only` | Approved tasks should inspect, analyze, and return a plan or text-only proposal. |
| `local_tools` | Approved tasks may use the Part 2 tools with existing safety checks. |

### Mode Matrix

| `HUB_EXECUTION_MODE` | `HUB_APPROVED_TASK_RUNNER` | `HUB_APPROVED_TASK_TOOL_MODE` | Behavior |
| --- | --- | --- | --- |
| `review_only` | *(ignored)* | *(ignored)* | Proposals and text only; no local execution |
| `manual_approval` | `placeholder` | *(ignored)* | Queue/approve flow; no real local execution |
| `manual_approval` | `part2_agent` | `read_only` | Approved local analysis only; no edits |
| `manual_approval` | `part2_agent` | `local_tools` | Approved local tool use with bash/read/edit/create tools |

The default and safest configuration is:

```env
HUB_APPROVED_TASK_RUNNER=placeholder
HUB_APPROVED_TASK_TOOL_MODE=read_only
```

To allow approved tasks to run through the local Part 2 SWE-agent:

```env
HUB_APPROVED_TASK_RUNNER=part2_agent
HUB_APPROVED_TASK_TOOL_MODE=local_tools
```

This only happens after a hub task has been queued and approved locally with `/approve TASK_ID`.

## Hub Smoke Test

Check hub connectivity without posting:

```bash
python -m src.hub.hub_client
```

Expected result:

```text
Hub stats:
{...}

Fetched X messages.
```

## Hub Loop

Start the safe hub loop:

```bash
python -m src.hub.hub_loop
```

On startup, the agent:

- validates hub configuration,
- fetches existing messages,
- starts from the latest existing sequence number,
- starts local runtime controls,
- polls only for newer messages.

During each polling cycle, it:

- ignores old messages and its own messages,
- responds only when mentioned by name,
- detects collaboration intent,
- skips unsupported intents,
- respects pause and response-limit controls,
- sanitizes the response,
- either prints the response in dry-run mode or posts it in live mode.

## Runtime Controls

While `src.hub.hub_loop` is running, type these commands into the local console:

| Command | Effect |
| --- | --- |
| `/status` | Print current pause state, response limit, and token limit |
| `/pause` | Keep polling but stop posting responses |
| `/resume` | Allow posting again |
| `/tokens N` | Set the runtime LLM response token cap |
| `/responses N` | Set the response cap for the current run |
| `/tasks` | List pending hub tasks waiting for local approval |
| `/approve TASK_ID` | Approve a queued hub task and pass it to the configured approved task runner |
| `/reject TASK_ID` | Remove a queued hub task without running it |
| `/quit` | Stop the hub loop cleanly |

These controls are local only. They do not expose tool access through the hub.

## Hub Collaboration Behavior

The hub agent recognizes these intents:

| Intent | Behavior |
| --- | --- |
| `review` | Provides feedback on shared code or proposals |
| `plan` | Helps coordinate next steps |
| `status` | Reports availability or progress |
| `help` | Offers software-engineering assistance |
| `question` | Answers relevant project questions |
| `code_request` | Shares a text-only code suggestion or patch-style snippet |
| `execute_task` | Creates a safe task proposal instead of executing immediately |
| `delegate_task` | Creates a delegation proposal for splitting work |

Messages that do not match a supported collaboration intent are ignored even if they mention the agent.


## Dynamic Group Collaboration

The hub agent supports optional group mention handling for multi-agent collaboration.

This is controlled by:

```env
HUB_ENABLE_GROUP_MENTIONS=false
```

When enabled, the agent may respond to broad group messages such as:

```text
@all agents build a small todo CLI app together
```

Group mention support is intentionally optional because if every agent replies to every group message, the hub can become noisy and unproductive.

## Coordination-First Group Behavior

For broad group tasks, the agent does not immediately start implementing.

Instead, it uses a coordination-first response strategy:

```text
group task
-> detect group mention
-> detect intent
-> choose temporary collaboration role
-> suggest task ownership and scope agreement
-> avoid duplicate work
-> wait for a clear assigned task before execution
```

This helps avoid common multi-agent problems:

- multiple agents building the same thing
- multiple competing plans
- several agents trying to lead at the same time
- unclear task ownership
- agents executing before scope is agreed

## Dynamic Temporary Roles

The agent is not hardcoded as a leader, coder, reviewer, or tester.

For each relevant message, it can choose a temporary collaboration role based on context:

| Role | Purpose |
| --- | --- |
| `planner` | Help define scope and safe next steps |
| `implementer` | Take one clear assigned task after local approval |
| `reviewer` | Review code, plans, or task splits |
| `tester` | Suggest or run safe verification steps |
| `coordinator` | Reduce duplicate work and clarify task ownership |
| `clarifier` | Ask focused questions when scope is unclear |
| `observer` | Avoid unnecessary noise unless a useful contribution is clear |

For example, a broad group task may make the agent choose a coordinator role, while a review request may make it choose a reviewer role.

## Task Claim Suggestions

For group collaboration, the agent can suggest how it may contribute without permanently claiming work.

Example:

```text
Possible contribution: I can help stabilize the collaboration by summarizing the active plan, identifying unclaimed tasks, and suggesting a small task split. I will not take over leadership unless the group asks.
```

This keeps the agent useful without creating coordination chaos.

The agent should only execute local work after:

1. A clear task is assigned.
2. The task is queued locally.
3. The user approves it in the console.
4. The approved task is run through the configured approved task runner.


## Task And Delegation Policy

If a hub message asks the agent to implement, fix, update, or modify code, the agent creates a task proposal instead of acting on the request.

Example message:

```text
@lullo-swe-agent implement Docker instructions in README
```

Expected behavior:

```text
TASK PROPOSAL

Requested by: ...
Assigned agent: lullo-swe-agent
Detected intent: execute_task

Safe plan:
1. Clarify the goal and expected output.
2. Identify the smallest safe change or contribution.
3. Share a text-only patch or implementation proposal in the hub.
4. Wait for local approval before any file edits or command execution.

Current execution mode: review_only
```

If a hub message asks for delegation, the agent can fetch hub stats and include known active agents in a delegation proposal. If stats are unavailable, it safely falls back to an empty agent list.

## Code Exchange Policy

The hub agent may share:

- small code snippets,
- patch-style suggestions,
- review comments,
- implementation proposals.

The hub agent must not:

- automatically execute code from hub messages,
- automatically apply patches from other agents,
- run bash based on hub messages,
- edit local files based on hub messages,
- reveal `.env`, API keys, passwords, private URLs, or private configuration.

Code exchange is treated as collaboration text, not trusted executable input.

## Response Guard

Before a hub response is printed or posted, `src/hub/hub_response_guard.py`:

- trims whitespace,
- replaces empty responses with a safe fallback,
- blocks obvious secret or config-related content,
- limits responses to 1500 characters.

Current hub response flow:

```text
Hub message
-> mention filter
-> intent filter
-> task/delegation/simple/LLM responder
-> response guard
-> dry-run print or live post
```

## Docker

Build the image:

```bash
docker build -t assignment2-part3-agent .
```

Run the hub loop using local environment variables:

```bash
docker run -it --rm --env-file .env assignment2-part3-agent
```

The Dockerfile starts the safe hub loop by default:

```text
python -m src.hub.hub_loop
```

The `.env` file is excluded from the image by `.dockerignore`.

## Assignment Requirement Mapping

| Requirement | Implementation |
| --- | --- |
| Shared hub communication | `src/hub/hub_client.py` and `src/hub/hub_loop.py` use the hub REST API |
| Avoid replying to every message | Startup sequence tracking, own-message filtering, mention filtering, and intent filtering |
| Team-player behavior | `src/hub/hub_responder.py`, task proposals, and delegation proposals |
| Secret protection | `config/system_prompt.md` and `src/hub/hub_response_guard.py` |
| Rate limiting | `HUB_POLL_INTERVAL_SECONDS` and sleeps between GET/POST requests |
| Runtime control | `src/hub/hub_runtime_controls.py` |
| Token control | `HUB_RESPONDER_MAX_TOKENS` and `/tokens N` |
| Code exchange | Text-only code suggestions and patch-style proposals |
| No unsafe hub tool access | Hub messages cannot call bash, file editing, the tool registry, or the SWE-agent loop |
| Local approval bridge | `HUB_EXECUTION_MODE`, `HUB_APPROVED_TASK_RUNNER`, and `/approve TASK_ID` keep hub-originated execution behind local approval |
| Docker support | `Dockerfile` and `.dockerignore` |
| Hub downtime robustness | `RequestException` handling keeps the loop alive after request failures |

## Known Limitations

- The local SWE-agent is intentionally conservative and may block commands that could be safe in other contexts.
- Session history is in memory for one run only.
- Hub collaboration is text-only; it does not automatically execute or apply work from other agents.
- The response guard is a simple defensive layer, not a complete secret scanner.
- `part2_agent` mode can run approved hub tasks through the local Part 2 SWE-agent, but only after explicit local console approval.

## Safety Note For `part2_agent` Mode

When `HUB_APPROVED_TASK_RUNNER=part2_agent`, approved tasks may use the existing Part 2 agent loop.

This means the Part 2 agent may request tools such as:

- `bash`
- `read_file`
- `edit_file_section`
- `create_file`

These tool calls still go through the existing Part 2 safety layers, including bash safety, path safety, output limiting, and max step limits.

This mode should only be enabled when the user wants locally approved hub tasks to be executed by the local SWE-agent.

## Demo

See `DEMO.md` for a shorter walkthrough of local and Docker demo commands.

## Approved Local Task Execution

The hub agent can run locally approved hub tasks through the Part 2 SWE-agent when manual approval and the Part 2 runner are enabled.

This is controlled by:

```env
HUB_EXECUTION_MODE=manual_approval
HUB_APPROVED_TASK_RUNNER=part2_agent
HUB_APPROVED_TASK_TOOL_MODE=local_tools
```

The execution flow is:

```text
Hub execute_task message
-> detect execute_task intent
-> create TASK PROPOSAL
-> add task to local approval queue
-> user approves locally with /approve TASK_ID
-> approved task is sent to the Part 2 SWE-agent
-> Part 2 agent may use its existing tools
-> final result is returned locally
```

The hub cannot directly trigger tool execution. A task must first be approved locally.

In `local_tools` mode, the approved task can use the existing Part 2 tools:

- `bash`
- `read_file`
- `edit_file_section`
- `create_file`

These tools still go through the Part 2 safety layers:

- bash safety checks
- path safety checks
- blocked sensitive paths
- output limiting
- max agent steps

This means the agent can make real local changes, but only after local approval and only through the existing safety system.

---

*Built as part 3 of a course assignment, May 2026.*
