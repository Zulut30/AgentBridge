# AgentBridge v0.1

AgentBridge - это локальный gateway между Cursor и локальными coding-агентами. Cursor подключается к AgentBridge как к OpenAI-compatible backend, а AgentBridge маршрутизирует запросы в Grok Build CLI или Codex CLI.

```text
Cursor
  -> https://<quick-tunnel>.trycloudflare.com/v1
  -> AgentBridge
     -> @grok  -> Grok Build CLI
     -> @codex -> Codex CLI
     -> @both  -> оба агента параллельно
```

## Возможности MVP

- OpenAI-compatible endpoints: `/v1/models`, `/v1/chat/completions`, `/v1/responses`.
- AgentBridge endpoints: `/agentbridge/status`, `/agentbridge/limits`, `/agentbridge/auto`.
- Простая авторизация через Bearer token.
- Роутинг команд `@grok`, `@codex`, `@both`, `@auto`.
- Model presets для выбора модели и reasoning level из Cursor.
- YAML-конфиг для CLI-команд, аргументов и timeout.
- Markdown skills, которые добавляются в системный prompt.
- Базовая safety policy против опасных команд и prompt-паттернов.
- Локальный usage log для учета запросов, времени выполнения и soft-limits.
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
  require_api_key: true
  allow_any_bearer: false

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
    model_arg: "-m"
    reasoning_effort_arg: "--reasoning-effort"
    dynamic_args_before_static: true
    args:
      - "-p"

  codex:
    enabled: true
    command: "codex"
    timeout_seconds: 1200
    mode: "exec"
    prompt_via_stdin: true
    model_arg: "-m"
    reasoning_effort_arg: null
    dynamic_args_before_static: true
    args:
      - "exec"

routing:
  default_agent: "auto"
  web_search_agent: "grok"
  code_agent: "codex"
  web_search_keywords:
    - "x"
    - "x.com"
    - "twitter"
    - "tweet"
    - "latest"
    - "today"
    - "news"
    - "search web"
    - "web search"

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

usage:
  enabled: true
  path: ".agentbridge/usage.jsonl"
  daily_request_limit: 200
  daily_seconds_limit: 7200
```

CLI-флаги не захардкожены в коде. Меняйте `agents.grok.command`, `agents.grok.args`, `agents.codex.command` и `agents.codex.args` под установленные версии Grok Build CLI и Codex CLI. Для Windows `.cmd` shim рекомендуется `prompt_via_stdin: true`, чтобы multiline prompt не обрезался shell-оберткой.

`model_arg` и `reasoning_effort_arg` добавляют динамические CLI-флаги на основе выбранного Cursor model id. Grok Build поддерживает `--reasoning-effort`; Codex CLI `exec` в текущей версии поддерживает `--model`, а reasoning передается в prompt metadata.

Если ваша версия Cursor хранит OpenAI key только в encrypted secret storage и не принимает plaintext row, для локального `127.0.0.1` можно включить `server.allow_any_bearer: true`. Тогда AgentBridge принимает любой Bearer token, но все равно требует наличие заголовка `Authorization`.

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
https://<quick-tunnel>.trycloudflare.com/v1

API Key:
local-dev-key

Model:
agentbridge-auto
```

Можно настроить Cursor автоматически из репозитория:

```bash
python -m app.tools.configure_cursor --force --open
```

Если Cursor возвращает `Access to private networks is forbidden`, используйте публичный HTTPS-туннель:

```bash
python -m app.tools.configure_cursor --tunnel cloudflared --force --open
```

Эта команда запускает `npx cloudflared tunnel --url http://127.0.0.1:8787`, ждет URL вида `https://*.trycloudflare.com`, прописывает его в Cursor как OpenAI-compatible Base URL и сохраняет логи туннеля в `.agentbridge/tunnel/`.

Команда:

- делает backup Cursor `state.vscdb`;
- включает OpenAI-compatible Base URL; с `--tunnel cloudflared` это публичный HTTPS URL `https://*.trycloudflare.com/v1`;
- записывает API key из `.env`;
- добавляет все `models.presets` в Cursor model picker;
- выбирает `agentbridge-auto` для существующих Cursor modes.

Перед обычным использованием лучше закрыть Cursor и запустить команду без `--force`. `--force` нужен только если вы сознательно пишете настройки при запущенном Cursor.

## Выбор модели и reasoning

Cursor выбирает модель через model id. AgentBridge понимает preset ids из `agentbridge.yaml`.

Примеры:

```text
agentbridge-auto
agentbridge-grok
agentbridge-codex
agentbridge-auto-gpt-5.5-medium
agentbridge-auto-gpt-5.5-high
agentbridge-auto-gpt-5.5-xhigh
agentbridge-auto-gpt-5.5-high-fast
agentbridge-auto-gpt-5.6-sol-medium
agentbridge-auto-gpt-5.6-sol-high
agentbridge-auto-gpt-5.6-sol-xhigh
agentbridge-auto-gpt-5.6-sol-high-fast
agentbridge-auto-gpt-5.4-high
agentbridge-auto-gpt-5.3-codex-high
agentbridge-codex-gpt-5.3-codex-high
agentbridge-grok-build-high
```

Если выбран preset с `target_model`, AgentBridge передает модель в CLI через `model_arg`. Если выбран preset с `reasoning_effort`, AgentBridge передает effort в Grok CLI через `reasoning_effort_arg` и всегда добавляет effort в prompt metadata.

Если модель вроде `gpt-5.6-sol` еще недоступна в конкретном CLI/backend, CLI вернет понятную ошибку, а AgentBridge отдаст ее обратно в Cursor.

## Что делает agentbridge-auto

`agentbridge-auto` не является отдельной моделью. Это routing preset:

- `@grok`, `@codex`, `@both`, `@auto` в prompt всегда имеют приоритет.
- Без явной команды coding-задачи идут в `routing.code_agent` (`codex`).
- Запросы с `x`, `x.com`, `twitter`, `tweet`, `latest`, `today`, `news`, `web search` идут в `routing.web_search_agent` (`grok`).
- Grok Build web search включен по умолчанию, если вы сами не добавили `--disable-web-search` или запрет `web_search`.

Проверить текущие правила:

```bash
curl -H "Authorization: Bearer local-dev-key" http://127.0.0.1:8787/agentbridge/auto
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

Возвращает все включенные `models.presets`, включая `agentbridge-auto`, `agentbridge-grok`, `agentbridge-codex`, GPT/Codex variants и Grok variants.

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

### `GET /agentbridge/status`

Возвращает project root, доступность CLI, model presets, auto-routing rules и usage summary.

### `GET /agentbridge/limits`

Возвращает локальную сводку usage log за текущий UTC-день:

- сколько запросов прошло через AgentBridge;
- сколько секунд заняли агенты;
- разбивку по agent/model;
- остаток по soft-limits из `usage.daily_request_limit` и `usage.daily_seconds_limit`.

Это локальный счетчик AgentBridge, а не официальный счетчик лимитов Grok/Codex аккаунта.

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
