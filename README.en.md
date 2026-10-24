# Discord Personal Archive

**Language / 语言:** [🇬🇧 English (current)](README.en.md) · [🇨🇳 简体中文](README.md)

**📖 Complete documentation:** [English User Guide](docs/guide.en.md) · [中文完整指南](docs/guide.zh-CN.md)

> A local-first Discord message archive and AI-powered personal knowledge base. Import messages **you sent**, search across channels, threads, and DMs, and summarize them with local Ollama or an OpenAI-compatible API.

**Version: v0.1.0 (early preview)** · Windows 10/11, Linux, macOS · Python 3.11+ · Vue 3 + FastAPI + SQLite

## Features

| Feature | Details |
| --- | --- |
| Official export import | Imports Discord data-package ZIP files (JSON or legacy CSV) and legacy cleaner preview JSON |
| Local archive | Deduplicates by message ID and stores content, channels, timestamps, and attachment links in SQLite |
| Vue web interface | Dashboard, message browser, cross-channel search, AI workspace, summaries, and import |
| Two AI providers | On-device Ollama or a user-configured OpenAI Chat Completions-compatible API |
| Optional live reader | Read-only Chrome extension for your own messages; **may violate Discord account rules** |
| Markdown output | Download AI summaries with traceable message IDs |

## Quick start

1. Download/extract the source and install **Python 3.11 or later**.
2. On Windows, double-click `start.bat`. On Linux/macOS, run `sh start.sh` from the project directory.
3. The launcher installs Python dependencies on first run. Open **http://127.0.0.1:8765**.
4. Request your data package from Discord under **User Settings → Data & Privacy**; import its ZIP in **数据导入 / Import**.
5. Search messages under **消息浏览 / Messages** and open **AI 工作台 / AI Workspace** to create summaries.

The built Vue app is included in `frontend/dist/`; Node.js is unnecessary for normal use.

### [→ Full English user guide](docs/guide.en.md)

### [→ 中文完整使用指南](docs/guide.zh-CN.md)

## Read before using the live connector

**Official Discord data exports are the recommended source.** They contain messages you sent, not deleted messages or complete conversation transcripts from other participants.

The optional extension reads the logged-in website's **user token** and calls Discord read endpoints. Discord explicitly **prohibits self-bot automation on normal user accounts**, including workflows that may lead to account termination. A read-only implementation is *not* official authorization. See [Discord's self-bot policy](https://support.discord.com/hc/en-us/articles/115002192352-Automated-User-Accounts-Self-Bots).

- The extension makes GET requests to Discord and cannot send, edit, or delete messages.
- Your Discord token is not sent to the local service or stored in SQLite; the local pairing code is not sent to Discord.
- The application binds to `127.0.0.1:8765` only. **Never port-forward or publicly expose it.**
- Cloud AI receives the selected message text; local Ollama uses a loopback connection.
- Treat `data/`, Discord exports, and API credentials as sensitive. Never commit them to public Git repositories.

The [English guide](docs/guide.en.md#8-security-and-platform-restrictions) includes coverage limits, troubleshooting, and privacy details.

## Repository layout

```text
backend/             FastAPI, ZIP/JSON parser, SQLite, summarization
frontend/src/        Vue 3 application source
frontend/dist/       Prebuilt static GUI (required for quick start)
extension/           Optional read-only Chrome MV3 companion
docs/                Full Chinese and English guides
tests/               Unit, integration, and simulated extension tests
run.py               Local server launcher
start.bat/start.sh   Windows and Unix launch scripts
```

## Development and tests

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python tests/integration_smoke.py
node tests/test_extension.mjs
```

Build the frontend with:

```bash
cd frontend
npm ci
npm run build
```

Automated tests use a local mock AI endpoint; they do not access a real Discord account or paid cloud API. Live Discord collection and real-model quality are **not yet verified with real credentials**.

## Inspiration and license

Inspired by an earlier Discord own-message cleaner's interface. The local archive service, Vue interface, and read-only scanner have been reimplemented without deletion capabilities. Licensed under [MIT](LICENSE).

---

**Language / 语言:** [English](README.en.md) · [简体中文](README.md) · [English Guide](docs/guide.en.md) · [中文指南](docs/guide.zh-CN.md)
