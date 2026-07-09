# Technical Audit

Date: 2026-07-09

## Scope

This audit covers the AgentBridge local OpenAI-compatible proxy, Cursor configuration flow, model routing, installation scripts, and verification commands.

## Current Status

- OpenAI-compatible endpoints are implemented: `/v1/models`, `/v1/chat/completions`, `/v1/responses`.
- Operational endpoints are implemented: `/health`, `/agentbridge/status`, `/agentbridge/auto`, `/agentbridge/limits`.
- Cursor can be configured automatically through `python -m app.tools.configure_cursor`.
- Cursor private-network blocking is handled through `python -m app.tools.configure_cursor --tunnel cloudflared`.
- Default Cursor model preset list contains broad AgentBridge wrappers for Auto, Grok, Codex, GPT, and Codex model families.
- Unsupported future model ids fall back to the selected CLI default model when the CLI rejects the explicit model id.
- Usage tracking is local JSONL under `.agentbridge/usage.jsonl`.
- Cross-platform install/run/check scripts exist for Windows PowerShell and POSIX shells.

## Local Verification Results

Environment: Windows, PowerShell, Python 3.13.

- `powershell -ExecutionPolicy Bypass -File .\scripts\check.ps1 -Server`: passed.
- `python -m unittest discover -s tests`: 13 tests passed.
- `python -m py_compile` over repository Python files: passed.
- `python -m app.tools.doctor --server`: passed local HTTP checks.
- `python -m app.tools.doctor --server --base-url <https tunnel root>`: passed tunnel HTTP checks.
- `/v1/models` returned 150 model ids.
- `/v1/chat/completions` returned a valid non-streaming OpenAI-compatible response.
- `/v1/responses` returned a valid OpenAI-compatible response.
- `/v1/chat/completions` with `stream: true` returned `text/event-stream` with one data chunk and `[DONE]`.
- Missing `Authorization` against `/v1/models` returned HTTP 401.
- Auto X/web prompt routed through Grok and returned a valid response.

POSIX shell scripts were added for macOS/Linux. This Windows host did not provide a usable POSIX shell for `sh -n`; run `./scripts/check.sh --server` on a macOS/Linux host before tagging a formal release.

## Verification Matrix

| Area | Command | Expected result |
| --- | --- | --- |
| Unit tests | `python -m unittest discover -s tests` | All tests pass |
| Python compile | `python -m py_compile <repo python files>` | No syntax errors |
| Local diagnostics | `python -m app.tools.doctor` | Required checks pass |
| Server diagnostics | `python -m app.tools.doctor --server` | Required HTTP checks pass |
| Models endpoint | `GET /v1/models` | Returns AgentBridge model list |
| Chat endpoint | `POST /v1/chat/completions` | Returns OpenAI-compatible response |
| Responses endpoint | `POST /v1/responses` | Returns OpenAI-compatible response |
| Auto routing | `GET /agentbridge/auto` | Shows Grok/Codex routing rules |
| Limits | `GET /agentbridge/limits` | Returns local usage summary |

## Known Runtime Constraints

- Grok and Codex CLIs are optional for installation but required for live agent execution.
- Cursor may reject `127.0.0.1` custom providers in some modes. Use the Cloudflare tunnel setup command in that case.
- Future model ids such as `gpt-5.6-sol` may not be accepted by the installed Codex CLI or account yet. AgentBridge retries without an explicit model when the CLI rejects the model id.
- `allow_any_bearer: true` should only be used for a loopback/local trusted setup or behind a temporary tunnel that you control.
- The Cloudflare Quick Tunnel URL is ephemeral and must be recreated when the tunnel process exits.

## Recommended Release Checklist

1. Run `scripts/check.ps1 -Server` on Windows or `scripts/check.sh --server` on macOS/Linux.
2. Verify `/v1/models` returns the expected model count.
3. Send one `agentbridge-auto` chat completion request.
4. Send one web/X query and confirm it routes to Grok in `.agentbridge/usage.jsonl`.
5. Confirm Cursor Base URL is HTTPS when Cursor reports private network blocking.
6. Confirm `.env`, `agentbridge.yaml`, `.agentbridge/`, and logs are not committed.
