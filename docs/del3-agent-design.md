# Del 3 Agent Design

## Goal

This agent is built for Assignment 2 Part 3. It participates in a shared multi-agent software engineering hub where several student agents communicate through a common group chat.

The goal is not to make the agent take over the project. The goal is to make it a safe, useful, and collaborative participant.

## Agent Role

The agent's default role is:

* safety-aware reviewer
* tester
* integration-support agent

The agent should not normally act as:

* solo programmer
* main implementer
* CLI owner
* README owner
* planner
* manager

The manager role is inferred from chat context. The agent may become manager only if a human prompt asks for a first-responder manager and this agent is clearly the first valid manager responder.

If another agent already posted a manager claim or protocol, this agent should stand down and behave as a worker/reviewer instead.

The agent can suggest small code snippets or patches when useful, but it should not act as the main implementation agent unless directly assigned.

## Current Architecture

The simplified hub flow is:

1. Fetch new messages from the hub.
2. Scan the fetched batch for human pause/resume control before normal message processing.
3. Ignore old messages, empty messages, and the agent's own messages.
4. Apply manager-selection safety so the agent does not compete with an existing manager claim.
5. Detect a lightweight keyword intent as a hint.
6. Use an LLM-based response decision gate to decide whether the agent should respond.
7. Generate a short, safe, text-only response.
8. Sanitize the response before printing or posting.
9. Respect runtime limits such as pause mode, max responses, token limits, and hub rate limits.

The Hell's Agents file-store flow is available as a separate entry point:

```bash
python3 -m src.hub.hub_tool_agent
```

That tool-use flow reads recent chat, the billboard, and the shared file list before acting. It can send short coordination messages, upload shared files, read shared files, or pass the turn. Code should be uploaded through the file store instead of pasted into chat.

## Response Decision Gate

The response decision gate decides whether the agent should respond to a message.

It returns:

* `should_respond`
* `reason`
* `response_type`

Example response types:

* `structure_project`
* `claim_review_task`
* `review_feedback`
* `test_plan`
* `integration_support`
* `code_suggestion`
* `clarify`
* `answer_question`
* `ignore`

This makes the agent more flexible than hardcoded mention-only routing, while still keeping the behavior controlled.

The final calibration makes the decision gate more conservative:

* default behavior is silence
* do not claim unassigned work from another agent's status summary
* do not compete with existing manager/protocol messages
* prefer ignoring a message over creating duplicate work
* respond mainly when directly mentioned, directly assigned, or explicitly asked for review/testing/integration support

## Responder Behavior

When the agent responds, it should provide visible value in the shared chat.

Useful contributions include:

* review notes
* test ideas
* integration risks
* concrete mismatch detection
* minimal code suggestions
* clear next steps

The responder should keep messages short, concrete, and focused. It should avoid generic replies, duplicate work, multi-file dumps, and unnecessary restructuring once code already exists.

## Collaboration Protocol

For broad all-agent kickoff messages, the agent may suggest or follow a lightweight protocol:

* `[CLAIM]` before starting work
* `[OUTPUT]` when sharing code, tests, or concrete results
* `[REVIEW]` when giving feedback
* avoid duplicate work
* prefer one minimal shared file structure
* switch from planning to integration review when code already exists

The agent should not automatically become coordinator just because the project lacks structure. It should only coordinate when the chat context clearly allows it or when it is directly asked.

## Safety Design

The agent is text-only in the hub by default.

It must not:

* reveal secrets, API keys, passwords, private URLs, or environment variables
* claim that it executed code unless it actually did
* claim that it edited files unless it actually did
* run local commands automatically from hub messages
* instruct other agents to run destructive commands
* spam the group chat

Local command execution, if used, must happen through local console/manual approval.

## Runtime Controls

The agent supports runtime controls such as:

* pause mode
* stop mode
* max responses per run
* max response tokens
* local task approval and rejection

Human pause/stop commands are handled in Python before LLM calls. The hub loop scans each fetched message batch for pause/resume before processing normal messages.

This helps control cost, prevent spam, and keep the agent safe during live group-chat tests.

## Final Calibration Changes

Based on real multi-agent hub testing and teacher feedback, the agent was calibrated for larger group collaboration.

The main issues observed during testing were:

* agents replying too often to status messages
* duplicate manager/protocol messages
* agents claiming open tasks from other agents' summaries
* replies continuing after human pause commands
* overly long code or test messages in the shared hub

The final design addresses these issues with:

* stricter decision prompt: default silence
* responder prompt: short, concrete, no broad volunteering
* batch-level pause/resume detection before LLM calls
* manager-selection safety before response generation
* no automatic claiming of unclaimed tasks from other agents' status summaries
* manual approval before local tools can run

## Hell's Agents File-Store Tool Use

The file-store tool agent uses four LLM tools:

* `send_message` for short coordination only
* `upload_file` for code or documentation
* `read_file` before reviewing or overwriting a shared file
* `pass_turn` when there is no useful action

This mode preserves the same team-player behavior: default silence, avoid duplicate work, respect the one-request-per-second hub limit, and keep chat messages short. It starts with `HUB_TOOL_MAX_MESSAGES=3`, below the server limit of 10 chat messages per agent.

## Known Limitations

The agent still has limitations:

* It does not have full persistent memory of the entire hub.
* It can miss some context if other agents only create local files and do not share their output.
* Manager race conditions can still happen in distributed chat.
* Behavior depends on model quality and hub timing.
* It may still respond too often if the max response limit is set too high.
* It may need prompt tuning to better detect concrete integration conflicts.
* It cannot verify code unless code or test output is shared in the hub.
* Tool execution results are local after approval unless manually shared back to the hub.

## Recommended Live Settings

For testing:

```env
HUB_DRY_RUN=true
HUB_MAX_RESPONSES_PER_RUN=4
HUB_USE_LLM_RESPONSE_DECISION=true
HUB_USE_LLM_RESPONDER=true
HUB_DECISION_MAX_TOKENS=200
HUB_RESPONDER_MAX_TOKENS=500
```

For controlled live use:

```env
HUB_DRY_RUN=false
HUB_MAX_RESPONSES_PER_RUN=4
HUB_USE_LLM_RESPONSE_DECISION=true
HUB_USE_LLM_RESPONDER=true
HUB_DECISION_MAX_TOKENS=200
HUB_RESPONDER_MAX_TOKENS=500
```
