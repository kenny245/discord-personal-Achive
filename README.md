# Discord Personal Archive（本地个人知识库）

**语言 / Language：** [🇨🇳 简体中文（当前）](README.md) · [🇬🇧 English](README.en.md)

**📖 详细使用指南：** [中文完整指南](docs/guide.zh-CN.md) · [English User Guide](docs/guide.en.md)

将自己在 Discord 服务器、频道、帖子和私信中发送的历史消息归档到本地 SQLite，再通过 Vue 3 GUI、FastAPI 和 Ollama / OpenAI 兼容模型进行搜索与总结。

> **账号风险：** 可选的在线读取扩展使用当前登录网页的 Discord 用户 Token。Discord 明确禁止普通用户账号 self-bot 自动化，可能导致账号限制或终止；限速也不能消除此风险。请优先使用官方数据包。本项目不包含消息删除功能。

## 功能

- 导入 Discord 官方个人数据 ZIP（JSON 或旧版 CSV），也支持旧版 Discord 清理器导出的 dsc-preview-v1 JSON。
- 自动识别可用的服务器/频道/帖子/私信/群聊元数据，根据消息 ID 去重，保留时间、正文、附件链接。
- 本地 Vue GUI 浏览来源、筛选和搜索消息；SQLite 保存数据及知识摘要。
- 按频道或整个归档分批总结，Ollama 保持消息在本机；OpenAI 兼容 API 则需要用户主动选择。
- 可选 Chrome 只读扫描伴侣：输入一次性本地配对码后，扫描自己发送的历史消息并同步到本机。

## Windows 10/11 启动

1. 安装 Python 3.11 或更新版。
2. 解压此项目的完整 ZIP，双击 **start.bat**。
3. 首次运行会建立虚拟环境并安装 Python 依赖（需要访问包索引）。
4. 服务启动后会自动打开 **http://127.0.0.1:8765**。

Linux/macOS 用户执行：**sh start.sh**。

服务仅绑定本机回环 IP，消息默认保存在项目内 data/archive.sqlite。可用环境变量 DPA_DATA_DIR 更改路径。发行 ZIP 包含已构建的 Vue 前端，因此正常使用不需要 Node.js。

## 导入消息的推荐路线

1. 在 Discord 的「用户设置 → 数据与隐私」申请个人数据包。
2. 下载 ZIP，不要手动解压。
3. 在本 GUI「数据导入」拖入 ZIP。
4. 检查消息后进入「AI 工作台」，选定范围和模型，生成知识摘要。

官方数据包只包含**自己发送**的历史消息，不包含其他参与者的完整回复；已删除的内容也不会出现。频道名称、帖子类型、置顶状态依赖实际导出字段。附件在此版本仅保存 URL，不会下载文件，链接未来可能失效。

## AI 接口

- **本地 Ollama**：预设本机服务 http://127.0.0.1:11434，示例模型 qwen3:4b。请提前安装 Ollama 并下载所选模型。
- **云端 OpenAI 兼容**：填写 API Base URL（例如 https://api.openai.com/v1）、模型 ID 和本次使用的 API Key。API Key 不写入数据库或配置文件；选择云端模式后，所选消息文本将发往服务提供商。

采用分组提炼和多轮归并。第一版单个任务最多读取**最近的 20,000 条消息**，可按频道分别总结更大归档；任务不支持跨服务重启恢复。AI 输出可能有错，请使用消息 ID 回查原文。

## 可选在线读取扩展

1. 启动本地 GUI，在「数据导入」页复制配对码。
2. Chrome 打开 chrome://extensions，启用开发者模式，加载本项目 extension 文件夹。
3. 保持 Discord 网页登录并进入具体频道，点击扩展图标。
4. 输入配对码，确认服务器/频道、时间范围和单轮上限，勾选账号风险提示后主动开始。
5. 扩展只向 https://discord.com/api/v10 发出 GET 读取请求；只把消息内容发送到 http://127.0.0.1:8765/api/collector。**不会把 Discord Token 发送到本地服务**。

请保持 Discord 标签页和扫描弹窗打开。Chrome Manifest V3 后台工作进程可能休眠，当前版本不支持断点自动续扫；已同步的消息可以去重再次导入。全服搜索受搜索索引与权限限制，不能保证完全覆盖所有历史。尚未用真实 Discord 账号做在线端到端验收。

## 开发与测试

- Python 后端：backend/
- Vue 前端：frontend/src/
- 可选只读扩展：extension/
- 单元测试：tests/

先执行 Python 命令 **python -m unittest discover -s tests -v**。

需要改动前端时，进入 frontend 目录运行 **npm install**，再运行 **npm run build**。发行包已带构建结果。开发时使用 Vite 可以设置 DPA_DEV=1 并执行 npm run dev。

## 安全边界

- 不编辑、不删除、不发送 Discord 消息；在线伴侣不包含任何向 Discord 发 DELETE 请求的代码。
- 导入器只读取官方 ZIP 的 messages 部分，不读取账号支付、登录会话等其他内容。
- 本地 HTTP 服务不对公网开放；提供本地来源校验、配对码、上传大小和 ZIP 解压上限。
- API 密钥和 Discord Token 不做持久化保存；本地 SQLite 与导出的摘要仍是敏感文件，请自行备份加密。
- 消息是可能包含恶意提示词的不可信材料，AI 端有明确的隔离提示；仍应人工核实重要结论。
- 这是单人本地工具，没有多用户登录系统，**不要进行路由器端口转发或反向代理公开访问**。

## 来源与授权

设计参考 mzrodyu/discord-self-message-cleaner（MIT）及上传的 discord-cleaner-pin-safe-0.6.3。新项目重新实现了只读扫描适配器，移除了旧版删除功能。MIT 许可见 LICENSE。

---

**语言切换 / Choose language：** [中文](README.md) · [English](README.en.md) · [中文使用指南](docs/guide.zh-CN.md) · [English Guide](docs/guide.en.md)
