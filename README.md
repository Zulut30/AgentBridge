# AgentBridge v0.1

AgentBridge - это локальный gateway между Cursor и локальными coding-агентами. Cursor подключается к AgentBridge как к OpenAI-compatible backend, а AgentBridge маршрутизирует запросы в Grok Build CLI или Codex CLI.

```text
Cursor
  -> http://127.0.0.1:8787/v1
  -> AgentBridge
     -> @grok  -> Grok Build CLI
     -> @codex -> Codex CLI
     -> @both  -> оба агента параллельно
```

## Возможности MVP

- OpenAI-compatible endpoints: `/v1/models`, `/v1/chat/completions`, `/v1/responses`.
- Простая авторизация через Bearer token.
- Роутинг команд `@grok`, `@codex`, `@both`, `@auto`.
- YAML-конфиг для CLI-команд, аргументов и timeout.
- Markdown skills, которые добавляются в системный prompt.
- Базовая safety policy против опасных команд и prompt-паттернов.
- Упрощенный streaming: один SSE chunk и затем `[DONE]`.

## Установка

Требуется Python 3.11+.

```bash
python -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt

cp .env.example .env
cp examples/agentbridge.yaml agentbridge.yaml
```

На Windows активация окружения:

```powershell
.\.venv\Scripts\Activate.ps1
```

## Конфиг

Основной файл конфигурации: `agentbridge.yaml`.

```yaml
server:
  host: "127.0.0.1"
  port: 8787
  api_key_env: "AGENTBRIDGE_API_KEY"

project:
  root: "/path/to/project"
  default_branch: "main"

agents:
  grok:
    enabled: true
    command: "grok"
    timeout_seconds: 1200
    mode: "headless"
    prompt_via_stdin: false
    args:
      - "-p"

  codex:
    enabled: true
    command: "codex"
    timeout_seconds: 1200
    mode: "exec"
    prompt_via_stdin: true
    args:
      - "exec"

routing:
  default_agent: "codex"

skills:
  enabled: true
  paths:
    - "./skills"
    - ".agentbridge/skills"

safety:
  readonly_by_default: true
  forbid_dangerous_commands: true
  forbidden_patterns:
    - "rm -rf /"
    - "DROP DATABASE"
    - "TRUNCATE"
    - "DELETE FROM"
    - "git push --force"
```

CLI-флаги не захардкожены в коде. Меняйте `agents.grok.command`, `agents.grok.args`, `agents.codex.command` и `agents.codex.args` под установленные версии Grok Build CLI и Codex CLI. Для Windows `.cmd` shim рекомендуется `prompt_via_stdin: true`, чтобы multiline prompt не обрезался shell-оберткой.

## Запуск

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8787
```

Проверка:

```bash
curl http://127.0.0.1:8787/health
curl -H "Authorization: Bearer local-dev-key" http://127.0.0.1:8787/v1/models
```

## Подключение в Cursor

Откройте:

```text
Cursor Settings -> Models -> Add custom OpenAI-compatible provider
```

Используйте:

```text
Base URL:
http://127.0.0.1:8787/v1

API Key:
local-dev-key

Model:
agentbridge-auto
```

## Примеры команд из Cursor

```text
@grok проанализируй архитектуру проекта и найди риски
```

```text
@codex исправь ошибку минимальным diff, без рефакторинга
```

```text
@both проверь, почему не работает авторизация через Telegram, и сравни выводы
```

```text
@codex напиши тесты для текущего бага, не меняя production-код
```

Если команда не указана, используется `routing.default_agent`. `@auto` также использует default routing.

## API

### `GET /health`

Возвращает статус сервера, project root и доступность CLI-команд.

### `GET /v1/models`

Возвращает модели:

- `agentbridge-grok`
- `agentbridge-codex`
- `agentbridge-auto`

### `POST /v1/chat/completions`

Принимает OpenAI Chat Completions request:

```json
{
  "model": "agentbridge-auto",
  "messages": [
    {
      "role": "user",
      "content": "@codex explain this project"
    }
  ],
  "stream": false
}
```

### `POST /v1/responses`

Принимает минимальный Responses API request:

```json
{
  "model": "agentbridge-auto",
  "input": "@grok analyze auth risks",
  "stream": false
}
```

## Skills

AgentBridge загружает все `.md` файлы из путей `skills.paths` и добавляет их в prompt. Базовые skills:

- `skills/minimal-diff.md`
- `skills/web-development.md`
- `skills/no-dangerous-actions.md`

## Ошибки CLI

Если CLI не установлен, выключен в конфиге, завершился с ошибкой или превысил timeout, AgentBridge вернет понятный текст в ответ Cursor. Пример:

```text
AgentBridge could not run Grok CLI.

Agent: grok
Return code: None

Error:
command not found

Fix:
Install and login to Grok CLI, then retry.
```

## Ограничения MVP

AgentBridge v0.1 is not a full Cursor Agent replacement. It is a local routing gateway for CLI coding agents.

Current limitations:

- no MCP support yet;
- no browser automation yet;
- no native Cursor tool calls;
- no automatic diff apply;
- no web UI;
- no production auth;
- streaming is simplified;
- CLI flags may need adjustment per installed Codex/Grok version.

## Roadmap

### v0.2

- Git worktree isolation
- Task history in SQLite
- Better streaming
- Configurable routing rules
- Project profiles
- Skill auto-selection

### v0.3

- MCP support
- Context7 MCP
- Filesystem MCP
- Browser tool
- Test runner integration

### v0.4

- Web UI
- Parallel task dashboard
- Diff viewer
- Approval gates
- Browser screenshots

### v1.0

- Full AgentBridge workspace
- Codex/Grok/Antigravity support
- MCP aggregator
- Agent marketplace/skills
- Team policies

## Тесты

```bash
python -m unittest discover -s tests
```
