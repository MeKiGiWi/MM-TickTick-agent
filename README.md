Track: A+D

# TickTick AI Task Clarifier

![CLI Python](https://img.shields.io/badge/Interface-CLI%20%2F%20Python-blue)
![LLM OpenRouter](https://img.shields.io/badge/LLM-OpenRouter-orange)
![Integration TickTick](https://img.shields.io/badge/Integration-TickTick-success)
![Tool Calling](https://img.shields.io/badge/Agent-Tool%20Calling-purple)
![GTD Clarify](https://img.shields.io/badge/Workflow-GTD%20Clarify-lightgrey)

CLI AI agent for TickTick that can inspect tasks, find overload, clarify vague to-dos, and update the task system through real tool calls.

The project was built as an agent prototype around the GTD "Clarify" stage: instead of only chatting about productivity, the assistant can read the current task state in TickTick, suggest concrete next actions, and create or update tasks directly.

## Highlights

- TickTick-connected agent with real read/write actions through tool calling.
- Focus on GTD Clarify: detects oversized, vague, and overdue tasks.
- Supports task creation, updates, moves, completion, project listing, and subtask creation.
- Handles multi-project task search and Inbox aliasing for more stable task operations.
- Local CLI workflow with Docker-based startup and OAuth login flow.
- Includes fallback model support through OpenRouter.

## Problem

Personal task lists often degrade into a backlog of vague intentions:

- tasks are too large to start;
- titles are not actionable;
- deadlines become stale;
- users lose visibility into near-term overload.

A plain LLM chat is not enough here, because useful assistance requires access to the real state of the task system and the ability to modify it safely.

## Solution

This repository implements a CLI agent that combines:

1. LLM reasoning via OpenRouter
2. TickTick API integration with OAuth
3. a tool registry that exposes structured task operations to the model
4. runtime context rules for dates, timezone handling, and safer task disambiguation

The result is an assistant that can both analyze a task backlog and act on it.

## Core Capabilities

- Create a task
- Create a task with subtasks
- List tasks
- Get task details
- Create subtasks under an existing task
- Update task fields
- Update a task by text search when the exact id is unknown
- List projects
- List upcoming tasks
- Move a task between projects
- Mark a task as completed

## GTD Clarify Workflow

The system prompt is tuned for a concrete productivity scenario:

- show the user their tasks;
- identify tasks that are too large;
- point out non-actionable task titles;
- highlight overdue items;
- surface possible short-term overload when too many difficult tasks cluster together.

This makes the project more than a generic "chat with API" demo. It is a domain-shaped agent with an explicit operational workflow.

## Architecture

```text
User input
  -> CLI session
  -> OpenRouter chat completion
  -> tool selection by the model
  -> TickTick provider
  -> task/project operations
  -> formatted answer in the terminal
```

## Repository Structure

```text
app/
  chat/                System prompt and chat session entrypoints
  cli/                 Interactive CLI session and local commands
  config/              First-run setup and config bootstrap
  domain/              Pydantic models for tasks, projects, and app config
  llm/                 OpenRouter client and tool loop
  providers/ticktick/  TickTick OAuth, API client, mapping, and services
  storage/             Local config persistence
  tools/               Tool registry, handlers, search, and presentation layer
  utils/               JSON and timezone helpers

config.local.example.json
compose.yaml
Dockerfile
REFLECTION.md
Spec.md
```

## Tech Stack

- Python 3.10+
- Pydantic
- httpx
- OpenAI Python SDK
- OpenRouter
- TickTick API
- Docker Compose

## Getting Started

### Docker

```bash
docker compose build --no-cache app
docker compose run --rm --service-ports app
```

On the first run the app will:

- ask for your OpenRouter API key;
- ask for TickTick OAuth credentials;
- open or print the TickTick OAuth authorization URL;
- save the local config in `config.local.json`.

### Local Python

```bash
pip install -e .
python -m app
```

## Configuration

See [`config.local.example.json`](./config.local.example.json) for the expected local configuration format.

Important notes:

- `config.local.json` is intentionally excluded from git because it contains local secrets and tokens.
- the default TickTick Inbox reference is handled through the alias `"inbox"`;
- user timezone is used for relative dates like "today" and "tomorrow".

## Key Files

- [`app/cli/session.py`](./app/cli/session.py) - main interactive CLI loop
- [`app/chat/prompts.py`](./app/chat/prompts.py) - domain-specific system prompt
- [`app/llm/openrouter.py`](./app/llm/openrouter.py) - model client, retries, fallback models, tool loop
- [`app/tools/registry.py`](./app/tools/registry.py) - tool registration and execution
- [`app/tools/handlers.py`](./app/tools/handlers.py) - task-oriented tool handlers
- [`app/tools/task_search.py`](./app/tools/task_search.py) - disambiguation logic for task updates by search
- [`app/providers/ticktick/client.py`](./app/providers/ticktick/client.py) - high-level TickTick provider
- [`app/providers/ticktick/tasks.py`](./app/providers/ticktick/tasks.py) - task CRUD, moves, completion, subtask flow
- [`app/providers/ticktick/oauth.py`](./app/providers/ticktick/oauth.py) - OAuth login and localhost callback flow

## What Makes It Interesting

- The agent does not ask the user for internal TickTick IDs when it can resolve them itself.
- Inbox handling is normalized through a dedicated alias to reduce ambiguity.
- The tool loop supports multiple model attempts and fallback behavior for OpenRouter errors.
- Task presentation is separated from raw API payloads, which keeps model-facing outputs cleaner.
- The agent is intentionally shaped around a concrete GTD workflow instead of being a generic assistant shell.

## Known Limitations

- Multi-step task workflows can still be fragile on faster/smaller models.
- The project is optimized for a CLI prototype, not for production-grade security or observability.
- Reliable behavior depends on correct TickTick OAuth setup.
- There is no dedicated test suite in the repository yet.

## Resume-Friendly Summary

This project demonstrates:

- LLM agent design with tool calling
- external API integration with OAuth
- structured action execution against a real productivity system
- prompt design for a narrow domain workflow
- practical handling of ambiguity, retries, fallbacks, and date/time context

## Reflection

The original project reflection is available in [`REFLECTION.md`](./REFLECTION.md).
