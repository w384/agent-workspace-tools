# Local Workspace Tools

**Author:** tianh
**Version:** 0.0.6
**Type:** Tool plugin

## Description

Local Workspace Tools connects Dify to a protected Windows FastAPI service for safe file organization inside one configured workspace.

The plugin only bridges requests to the local service. It does not receive arbitrary Windows paths and does not perform direct filesystem operations in the Dify container.

## Features

- List workspace files with pagination.
- Search workspace files by name.
- Read file metadata and Base64 content when the file is within the configured content limit.
- Create a validated organization plan without changing files.
- Execute a plan only after Human Input approval.
- Upload a file only through the confirmed upload flow; existing files are never overwritten.
- Pass the current Dify runtime `user_id` to the local service for path authorization.

## Requirements

- A Windows FastAPI service running `dify-agent-workspace-tools`.
- A configured workspace root on the Windows host.
- Dify running in Docker Desktop or another environment that can reach the host service.
- The provider API key configured in Dify.

For Docker-hosted Dify and a Windows service listening on port 8890, use:

```text
http://host.docker.internal:8890
```

Do not use `localhost` for the Windows service address from inside a Dify container.

## Provider configuration

Configure the `Local Workspace` provider with:

- `Service URL`: the protected local service URL, such as `http://host.docker.internal:8890`.
- `API Key`: the service API key, entered only in Dify provider credentials.

The provider validates credentials through the protected file-list endpoint. Never place the API key in a workflow variable, model prompt, tool output, README, log, or source file.

## Recommended workflow

Use the tools in this order:

```text
list_files → LLM analysis → create_plan → Human Input → execute_confirmed_plan(plan_id, plan_hash)
```

The LLM may produce a candidate `operations_json`, but it must not receive or generate an API key or approval token. Preserve both `plan_id` and `plan_hash` from the same `create_plan` result through Human Input, then pass them unchanged to the execution tool. Do not regenerate or re-query the hash after confirmation. The execution tool belongs only on the Human Input approval branch. Rejection, cancellation, or timeout must end without a write operation.

For uploads, use a separate confirmed branch:

```text
Select file → Human Input → upload_file
```

The local service enforces workspace boundaries, user path permissions, file-size limits, and non-overwriting behavior.

## Security boundaries

- The local FastAPI service is the only filesystem execution boundary.
- Absolute paths, parent traversal, management directories, and unauthorized prefixes are rejected by the service.
- Plan execution rechecks the current user permissions before consuming the one-time approval token.
- Plan execution compares the independently preserved confirmation-time `plan_hash` before consuming the token or writing files.
- The plugin never exposes the approval token as a tool parameter or workflow variable.
- Knowledge bases, vector stores, graph stores, and complex Agentic RAG are outside this project.

## Documentation

- Workflow setup: `docs/dify/workflow-setup.md`
- Acceptance cases: `docs/dify/acceptance-cases.md`
- Project implementation plan: `docs/implementation-plan.md`
