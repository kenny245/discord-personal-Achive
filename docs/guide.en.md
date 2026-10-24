# Discord Personal Archive — Complete User Guide

**Choose language / 选择语言:** [🇬🇧 English (current)](guide.en.md) · [🇨🇳 简体中文](guide.zh-CN.md)

[← Project home](../README.en.md) · [中文项目首页](../README.md)

**Version: v0.1.0 (early preview).** This guide covers Windows 10/11, Linux, and macOS.

> **Start with your official Discord data package.** The optional live scanner automates a normal Discord user account, which Discord forbids as self-bot activity even when requests are read-only. See [Section 8](#8-security-and-platform-restrictions) before considering that feature.

## 1. What the application does

Discord Personal Archive is a personal knowledge base that runs on **your own computer**. It is not an official Discord bot, cloud-hosted archive, or full server backup.

| Component | Purpose | Required? |
| --- | --- | --- |
| FastAPI local server | Data import, search, AI jobs, summary downloads | Yes |
| SQLite database | Keeps messages and summaries, deduplicated by message ID | Yes; created automatically |
| Vue 3 web GUI | Browse/search messages, select models, review reports | Yes; prebuilt assets included |
| Chrome read-only companion | Optionally scan your own historical messages online | No; carries account-policy risk |

The tool can organize messages you sent in server text channels, threads, direct messages, group DMs, and other locations represented in an official export. It **does not recover other people's messages** to reconstruct full conversations.

Records retain message IDs, timestamps, text, attachment links, channel information, and extra metadata when available. Channel titles, thread classification, or pinned flags may be absent when Discord does not provide them.

## 2. Installation and launch

### 2.1 Requirements

- Windows 10/11, Linux, or macOS.
- **Python 3.11 or newer**, with network access during first-time dependency installation.
- A modern browser (Chrome or Edge recommended).
- No Node.js required for normal use: `frontend/dist/` is included.
- [Ollama](https://ollama.com/) and a downloaded model if you want fully local AI summarization.

### 2.2 Windows — recommended

1. Download the GitHub source ZIP, or clone the repository.
2. Extract **the entire project directory** to a writable location such as `D:\Tools\Discord-Personal-Archive`.
3. Install Python 3.11+ and check it in PowerShell:

   ```powershell
   py -3 --version
   ```

4. Double-click `start.bat` in the project root. On first launch, it creates a `.venv` environment and installs Python packages.
5. The browser should open **http://127.0.0.1:8765**. If it does not, enter the address manually.
6. Close the launch window to stop the local service. Run the script again the next time you need it.

If setup fails, read the terminal error and confirm that the `py` launcher is installed and Python packages can be downloaded.

### 2.3 Linux / macOS

From the project root:

```bash
python3 --version
sh start.sh
```

To launch manually:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python run.py
```

The interface is available at **http://127.0.0.1:8765**.

### 2.4 Where data is stored

The default SQLite database is `data/archive.sqlite`. SQLite uses write-ahead logging, so `archive.sqlite-wal` or related files may exist while the server is running.

**Stop the service before making a filesystem backup, then copy the entire `data/` directory.** You may override its location with the `DPA_DATA_DIR` environment variable. Never commit private archive data to GitHub.

## 3. Import your Discord history — recommended

### 3.1 Request an official data package

1. Open Discord.
2. Go to **User Settings → Data & Privacy**.
3. Find **Request Data / Request My Data** and include message data in your request.
4. Discord sends a download link to your account email when your export is ready; processing can take **up to 30 days**.
5. Download the ZIP containing the `messages` directory. **Do not extract it before importing, and do not upload it to untrusted websites.**

Official help:

- [Your Discord Data Package](https://support.discord.com/hc/en-us/articles/360004957991-Your-Discord-Data-Package)
- [Requesting a Copy of your Data](https://support.discord.com/hc/en-us/articles/360004027692-Requesting-a-Copy-of-your-Data)

### 3.2 Import in the GUI

1. Start the local application.
2. Open **数据导入 (Import)** from the left navigation.
3. Choose the official ZIP file.
4. Wait for the confirmation showing messages **added**, **updated**, and **sources found**.
5. Open **总览 (Overview)** to check totals; then search for a phrase you remember sending in **消息浏览 (Message Browser)**.

The parser reads only the `messages` section of the official archive; account, payment, and other directories are not imported. ZIP entries are parsed without extracting paths onto your disk.

Supported formats: current Discord message JSON, legacy CSV, and the older cleaner's `dsc-preview-v1` preview JSON, including ZIP archives containing that preview format.

### 3.3 File limits and duplicate imports

Version 0.1.0 currently enforces:

| Limit | Maximum |
| --- | --- |
| Uploaded archive | **250 MB** |
| Combined uncompressed ZIP contents | **1 GB** |
| Any individual ZIP file | **128 MB** |
| Number of ZIP entries | **20,000** |

There is no automated multi-part importer yet. If your official export exceeds these limits, create smaller import archives while preserving the expected Discord `messages` directory structure.

Messages are deduplicated by their Discord message IDs. Reimporting an archive updates matching records instead of creating duplicates. Conflicting channel mappings for the same ID cause an import error to protect consistency.

### 3.4 Why some content may be missing

- **Other participants' messages:** Your personal export does not contain full transcripts of other people's replies.
- **Deleted messages:** An export does not restore messages that were deleted.
- **Unavailable servers/channels:** Location metadata may be incomplete if access changed.
- **Attachments:** Only attachment **URLs** are saved; the app does not download binary files, and links may expire.
- **Unknown source:** Some archives lack channel-type metadata. The message can still be searchable.

## 4. Using the Vue GUI

**The v0.1.0 interface itself currently uses Chinese labels.** These repository user guides are available in English and Chinese; fully localized GUI labels are not implemented yet.

| Chinese navigation label | English meaning | What to do there |
| --- | --- | --- |
| **总览** | Overview | Check message counts, categories, and recent summaries |
| **消息浏览** | Message Browser | Search text, channel names, or message IDs; filter by source |
| **知识摘要** | Knowledge Summaries | Read and download previously generated reports |
| **AI 工作台** | AI Workspace | Select scope and model; launch summarization |
| **数据导入** | Import & Sync | Import files or obtain the local extension pairing code |

A practical first walkthrough:

1. Import a modest official data package.
2. Search for a project name or technical term under **消息浏览**.
3. Select an individual channel or DM to narrow the results.
4. Open **AI 工作台** and choose the same source as your analysis scope.
5. After completion, review the report in **知识摘要** and verify important statements against message IDs.

Search covers **your imported local archive**. It does not query every Discord server live.

## 5. AI summaries: local Ollama or cloud API

### 5.1 What the summarizer does

For each user-initiated job, the application selects **up to the most recent 20,000 stored messages** in the chosen scope. It builds smaller batches with timestamps, channel names, and message IDs, extracts themes/decisions/tasks/resources, and merges the batch outputs into a final report.

Important limitations:

- Empty sources cannot be summarized.
- Very long individual messages are truncated for analysis.
- The result is model-generated and may omit facts or misread context; inspect original message IDs.
- Only one AI job may be active at a time. Jobs do not resume across server restarts.
- Jobs are started by clicking **生成知识摘要 (Generate Summary)**; unattended scheduling is **not implemented**.

### 5.2 Ollama — keep message processing local

1. Install and start [Ollama](https://ollama.com/).
2. Download a model, for example:

   ```bash
   ollama pull qwen3:4b
   ```

3. Ensure the Ollama server is running at `http://127.0.0.1:11434`. Depending on your setup, you may need `ollama serve`.
4. In **AI 工作台**, select **本地 Ollama**.
5. Enter:

   - **服务端点 / Endpoint:** `http://127.0.0.1:11434`
   - **模型 / Model:** `qwen3:4b`
   - **分析范围 / Scope:** all messages or one channel/DM

6. Optionally set a report title and click **生成知识摘要**.
7. Watch progress, then review the result under **知识摘要**.

Your model name must match a model actually installed in Ollama. Performance, memory use, and summary quality depend on your system and model.

### 5.3 OpenAI Chat Completions-compatible service

1. Select **兼容云端 API** in **AI 工作台**.
2. Enter your provider's **API Base URL**, e.g. `https://api.openai.com/v1`.
3. Enter its model ID and an API Key valid for that provider.
4. Choose the messages to analyze, then explicitly start the job.

**Privacy warning:** The selected message text, timestamps, and related identifiers are transmitted to **the endpoint you supply**. Review the provider's privacy policy, data retention, and costs before proceeding. Do not send private records to an unknown proxy.

The client sends OpenAI-style **Chat Completions** requests to `POST /chat/completions`. Some services marketed as “OpenAI-compatible” differ in supported fields; compatibility is not guaranteed with every provider or model.

External providers must use **HTTPS**. Plain HTTP is permitted only for a loopback-hosted compatible service.

API Keys remain in the running job's memory and are not persisted to SQLite or an on-disk settings file. Never paste credentials into bug reports or screenshots.

### 5.4 Export a report

Under **知识摘要**, select a summary and click **Markdown**. The generated document may contain major themes, decisions, follow-up items, and useful resources. Message IDs help trace claims to their archived sources.

## 6. Optional read-only live collection — account risk

**Experimental feature. Not recommended as your primary import method.** Discord's automation policy applies even if the extension never edits or deletes content.

### 6.1 Install the Chrome extension

1. Keep the local archive service running.
2. Navigate to `chrome://extensions` and enable **Developer mode**.
3. Click **Load unpacked** and select the full `extension/` folder.
4. Open **https://discord.com/channels/** while logged into your own account, and navigate to a specific server channel, thread, or DM.
5. In the local GUI, open **数据导入** and copy the **local pairing code**.
6. Open the extension popup and paste that code.

This temporary pairing code authorizes the extension to submit records to **your local server**. It changes on service restart; it is **not** your Discord login token.

### 6.2 Set the collection scope

1. Use the popup's current-conversation autofill control and verify the server/channel IDs.
2. To scan a DM, open that **specific DM conversation** first.
3. Configure start/end dates and a cap of **1–20,000 own messages per run**.
4. Read and check the account-risk confirmation.
5. Manually start the scan and watch the counts for scanned records, your own records, and locally saved messages.
6. Stop if you see errors, and check the imported sources in the main GUI afterward.

There are two scanning modes:

- **Specific channel, thread, or DM:** Reads channel pages and locally filters by the current account's author ID.
- **Entire server:** When the channel field is empty, uses the Discord server message-search endpoint with an author filter. Completeness depends on search indexing, account access, and API behavior.

Discord requests use **GET only**. The extension contains no send, edit, or delete actions. **Nevertheless, using a normal user token for automated collection is against Discord's self-bot policy.**

### 6.3 Reliability and rate limits

- Discord permissions, changing endpoints, search indexing, and HTTP 429 rate limits can interrupt a scan.
- Chrome Manifest V3 service workers may go idle. Keep the Discord tab and extension popup open.
- Persistent resume after browser restart is not implemented. Re-running a range is safe from message duplication because SQLite deduplicates by ID.
- The Discord user token is **never sent to the local archive endpoint**; only normalized own-message records, channel metadata, and the local pairing code are transmitted there.
- **The extension has only been verified with simulated browser and API responses; it has not passed a real-account Discord end-to-end test.**

## 7. Maintenance and troubleshooting

### 7.1 Back up or migrate your archive

Stop the service before copying `data/` to a trusted storage location. Restore it only while the service is stopped. Consider encrypting backups containing DMs, invitation links, personal contact details, or confidential notes.

When updating application code, preserve your existing `data/` directory.

### 7.2 Common issues

| Symptom | What to check |
| --- | --- |
| Windows launcher closes immediately | Run `start.bat` from a terminal and inspect Python/setup errors |
| “Vue has not been built” | Install Node.js 22; in `frontend/`, run `npm ci` followed by `npm run build` |
| Cannot connect to `127.0.0.1:8765` | Is the server window still running? Is port 8765 occupied? |
| Official ZIP fails to import | Confirm the `messages/` directory, archive type, and file-size limits |
| Ollama summary fails | Check Ollama is running, the model is downloaded, and the endpoint is correct |
| Cloud API returns 401/429 | Review the provider's API Key, quota, rate limit, and model permissions |
| Extension pairing fails | Confirm the local service is running and use its current pairing code |
| Fewer messages than expected | Exports contain your own messages only; live scanning also depends on access and indexing |
| Attachment links do not work | Only URLs are stored; original Discord links can expire |

### 7.3 Developer verification

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python tests/integration_smoke.py
node tests/test_extension.mjs
```

For frontend changes:

```bash
cd frontend
npm ci
npm run build
```

The integration test starts temporary localhost endpoints that emulate **both Ollama and an OpenAI-compatible API**. It does not require a real Discord user token or a paid AI API Key.

## 8. Security and platform restrictions

1. **Discord policy:** [Discord explicitly prohibits normal-user self-bots](https://support.discord.com/hc/en-us/articles/115002192352-Automated-User-Accounts-Self-Bots). Read-only behavior does **not** make the extension officially approved; account termination remains a risk.
2. **Scope:** The software is designed to archive **your own** messages only. It does not bypass channel permissions or collect other people's private messages, and it cannot guarantee a complete history.
3. **Local HTTP server:** Listens only on `127.0.0.1:8765` and performs origin/pairing checks, but has **no public-facing multi-user authentication**. Do not port-forward or publish it behind a reverse proxy.
4. **Credentials:** Neither Discord user tokens nor AI Keys are persisted by the application. Protect your browser profile and computer from untrusted extensions or malware.
5. **Cloud model privacy:** Text sent to a configured provider leaves your local machine. Only analyze records you are authorized to handle, and understand the provider's privacy and retention policies.
6. **Untrusted message content:** Historical chat messages can contain prompt-injection text. The summarizer instructs the model to treat them as data, but you must review consequential conclusions yourself.
7. **Sensitive storage:** SQLite and exported Markdown reports may contain private data. Store and erase them appropriately. `data/` is excluded by `.gitignore`.
8. **Not implemented:** Sending/editing/deleting Discord messages, downloading attachment binaries, multi-user accounts, scheduled unattended collection, resumable live scans, complete two-sided transcripts, or guaranteed real-account live compatibility.

When reporting a bug, **never attach live Discord tokens, API Keys, private DMs, or your unredacted official data package** to a public issue.

## 9. Implementation and license

- **Backend:** Python, FastAPI, SQLite; transactional imports and background AI jobs.
- **Frontend:** Vue 3 + Vite; the FastAPI service serves its prebuilt pages.
- **Optional browser extension:** Chrome Manifest V3, GET-only Discord requests, paired localhost synchronization.
- **License:** [MIT](../LICENSE).

GitHub Actions is configured to build the Vue frontend and run Python unit tests, local integration tests, and simulated extension tests. **Passing tests does not imply Discord has approved the extension or that it is safe to use on a live account.**

---

**Language / 语言:** [English](guide.en.md) · [简体中文](guide.zh-CN.md) · [Project README](../README.en.md)
