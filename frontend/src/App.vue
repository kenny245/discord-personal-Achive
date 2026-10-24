<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import {
  Activity, AlertCircle, ArrowRight, ArrowUpRight, BookOpen, Check,
  CheckCircle2, ChevronLeft, ChevronRight, Clock3, Cloud, Copy,
  Database, Download, FileArchive, Filter, FolderOpen, HardDrive,
  Hash, Inbox, KeyRound, Layers3, Link2, LoaderCircle, LockKeyhole,
  Menu, MessageCircle, MessagesSquare, RefreshCw, Search, Server,
  Settings2, ShieldAlert, ShieldCheck, Sparkles, UploadCloud, X,
} from '@lucide/vue'

const view = ref('overview')
const mobileMenu = ref(false)
const loading = ref(false)
const busyImport = ref(false)
const stats = ref({ messages: 0, channels: 0, summaries: 0, kinds: {}, last_import: null })
const channels = ref([])
const messages = ref({ items: [], total: 0, offset: 0, limit: 40 })
const summaries = ref([])
const selectedSummary = ref(null)
const activeChannel = ref('')
const sourceSearch = ref('')
const messageQuery = ref('')
const pairing = ref({ key: '', endpoint: '', expires: '' })
const importResult = ref(null)
const toast = ref({ message: '', tone: 'success' })
const aiProvider = ref('ollama')
const aiScope = ref('channel')
const aiChannel = ref('')
const aiModel = ref('qwen3:4b')
const aiEndpoint = ref('http://127.0.0.1:11434')
const aiKey = ref('')
const aiTitle = ref('')
const job = ref(null)
const errorDetail = ref('')
const nav = [
  { id: 'overview', label: '总览', icon: Layers3 },
  { id: 'messages', label: '消息浏览', icon: MessagesSquare },
  { id: 'summaries', label: '知识摘要', icon: BookOpen },
  { id: 'ai', label: 'AI 工作台', icon: Sparkles },
  { id: 'import', label: '数据导入', icon: UploadCloud },
]
const kindLabels = { guild: '服务器频道', thread: '帖子', dm: '私信', group_dm: '群聊', unknown: '待识别来源' }
const kindIcons = { guild: Server, thread: Hash, dm: MessageCircle, group_dm: MessagesSquare, unknown: FolderOpen }
const viewTitle = computed(() => nav.find(n => n.id === view.value)?.label || '总览')
const filteredChannels = computed(() => channels.value.filter(c =>
  [c.name, c.guild_name, c.id].join(' ').toLowerCase().includes(sourceSearch.value.toLowerCase())
))
const currentChannel = computed(() => channels.value.find(c => c.id === activeChannel.value))
const featuredMessages = computed(() => messages.value.items.slice(0, view.value === 'overview' ? 4 : 40))
const kindEntries = computed(() => Object.entries(stats.value.kinds || {})
  .filter(([, n]) => n > 0).sort((a, b) => b[1] - a[1]))
const aiRunning = computed(() => ['queued', 'running'].includes(job.value?.status))
const fmt = n => new Intl.NumberFormat('zh-CN').format(n || 0)
const date = text => text ? new Date(text).toLocaleString('zh-CN', { hour12: false }) : '未知时间'
const compactDate = text => text ? new Date(text).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' }) : '—'
const safeLink = url => { try { const u = new URL(url); return u.protocol === 'https:' ? u.href : null } catch { return null } }
const messageLink = msg => `https://discord.com/channels/${msg.guild_id || '@me'}/${msg.channel_id}/${msg.id}`
let pollTimer = null
let searchTimer = null
let toastTimer = null

async function api(path, options = {}) {
  const response = await fetch(path, options)
  if (!response.ok) {
    const error = await response.json().catch(() => ({}))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }
  return response.json()
}
function flash(message, tone = 'success') {
  toast.value = { message, tone }
  clearTimeout(toastTimer)
  toastTimer = setTimeout(() => { toast.value.message = '' }, 5000)
}
async function refresh() {
  loading.value = true
  try {
    const [s, c, p] = await Promise.all([
      api('/api/stats'), api('/api/channels'), api('/api/pairing'),
    ])
    stats.value = s
    channels.value = c
    pairing.value = p
    if (!aiChannel.value && c.length) aiChannel.value = c[0].id
    await Promise.all([loadMessages(), loadSummaries()])
    errorDetail.value = ''
  } catch (error) {
    errorDetail.value = error.message
    flash('无法连接本地归档服务：' + error.message, 'error')
  } finally { loading.value = false }
}
async function loadMessages() {
  const params = new URLSearchParams({ limit: '40', offset: String(messages.value.offset || 0) })
  if (activeChannel.value) params.set('channel_id', activeChannel.value)
  if (messageQuery.value.trim()) params.set('q', messageQuery.value.trim())
  messages.value = await api('/api/messages?' + params)
}
async function loadSummaries() {
  summaries.value = await api('/api/summaries')
  if (!selectedSummary.value && summaries.value.length) selectedSummary.value = summaries.value[0]
  else if (selectedSummary.value) selectedSummary.value =
    summaries.value.find(x => x.id === selectedSummary.value.id) || summaries.value[0] || null
}
function goto(target) {
  view.value = target
  mobileMenu.value = false
  if (target === 'messages') loadMessages().catch(e => flash(e.message, 'error'))
}
function openChannel(channel) {
  activeChannel.value = channel.id
  aiChannel.value = channel.id
  messages.value.offset = 0
  messageQuery.value = ''
  goto('messages')
}
function clearChannel() {
  activeChannel.value = ''
  messages.value.offset = 0
  loadMessages().catch(e => flash(e.message, 'error'))
}
function searchMessages() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    messages.value.offset = 0
    loadMessages().catch(e => flash(e.message, 'error'))
  }, 300)
}
function page(delta) {
  messages.value.offset = Math.max(0, messages.value.offset + delta * messages.value.limit)
  loadMessages().catch(e => flash(e.message, 'error'))
}
async function importFile(file) {
  if (!file || busyImport.value) return
  busyImport.value = true
  importResult.value = null
  try {
    const form = new FormData()
    form.append('file', file, file.name)
    importResult.value = await api('/api/import', { method: 'POST', body: form })
    flash(`导入成功：新增 ${fmt(importResult.value.added)} 条，更新 ${fmt(importResult.value.updated)} 条`)
    await refresh()
  } catch (error) { flash('导入失败：' + error.message, 'error') }
  finally { busyImport.value = false }
}
function fileChanged(event) {
  const file = event.target.files?.[0]
  if (file) importFile(file)
  event.target.value = ''
}
function fileDropped(event) {
  const file = event.dataTransfer?.files?.[0]
  if (file) importFile(file)
}
async function copyPairing() {
  try { await navigator.clipboard.writeText(pairing.value.key); flash('只读扫描扩展配对码已复制') }
  catch { flash('复制失败，请手动选中配对码。', 'error') }
}
watch(aiProvider, provider => {
  if (provider === 'ollama') {
    aiEndpoint.value = 'http://127.0.0.1:11434'
    aiModel.value = 'qwen3:4b'
  } else {
    aiEndpoint.value = 'https://api.openai.com/v1'
    aiModel.value = 'gpt-4.1-mini'
  }
})
async function startSummary() {
  if (aiRunning.value) return
  try {
    const response = await api('/api/summarize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        scope: aiScope.value, channel_id: aiScope.value === 'channel' ? aiChannel.value : null,
        provider: aiProvider.value, model: aiModel.value.trim(), endpoint: aiEndpoint.value.trim(),
        api_key: aiKey.value, title: aiTitle.value.trim(),
      }),
    })
    aiKey.value = '' // never persist, and clear after dispatch
    job.value = { id: response.job_id, status: 'queued', detail: '已排队', done: 0, total: 0 }
    flash('AI 分析任务已启动')
    clearInterval(pollTimer)
    pollTimer = setInterval(checkJob, 1400)
    await checkJob()
  } catch (error) { flash('启动失败：' + error.message, 'error') }
}
async function checkJob() {
  if (!job.value?.id) return
  try {
    const response = await api('/api/jobs/' + job.value.id)
    job.value = response
    if (['complete', 'failed'].includes(response.status)) {
      clearInterval(pollTimer)
      if (response.status === 'complete') {
        await loadSummaries()
        selectedSummary.value = summaries.value.find(s => s.id === response.summary_id) || selectedSummary.value
        flash('AI 知识摘要已生成')
      } else flash(response.detail || 'AI 任务失败', 'error')
    }
  } catch (error) { clearInterval(pollTimer); flash(error.message, 'error') }
}
function summaryOpen(summary) {
  selectedSummary.value = summary
  goto('summaries')
}
function downloadSummary(summary) {
  window.open('/api/summaries/' + summary.id + '/markdown', '_blank', 'noopener,noreferrer')
}
onMounted(refresh)
onUnmounted(() => {
  clearInterval(pollTimer)
  clearTimeout(searchTimer)
  clearTimeout(toastTimer)
})
</script>

<template>
  <div class="shell">
    <div v-if="mobileMenu" class="mobile-shade" @click="mobileMenu = false"></div>
    <aside class="sidebar" :class="{ 'sidebar-open': mobileMenu }">
      <div class="brand">
        <div class="brand-icon"><Database :size="23" :stroke-width="1.9" /></div>
        <div><strong>Personal Archive</strong><small>DISCORD KNOWLEDGE SPACE</small></div>
      </div>
      <div class="side-caption">工作空间</div>
      <nav class="primary-nav">
        <button v-for="n in nav" :key="n.id" class="nav-item" :class="{ active: view === n.id }" @click="goto(n.id)">
          <component :is="n.icon" :size="18" :stroke-width="1.8" />
          <span>{{ n.label }}</span>
          <ChevronRight v-if="view === n.id" :size="15" class="nav-chevron" />
        </button>
      </nav>
      <div class="side-section-heading">
        <span>会话来源</span>
        <span class="small-count">{{ fmt(channels.length) }}</span>
      </div>
      <label class="sidebar-search">
        <Search :size="15" /><input v-model="sourceSearch" placeholder="筛选频道或私信" aria-label="搜索会话来源">
      </label>
      <div class="sidebar-sources">
        <button v-for="c in filteredChannels.slice(0, 70)" :key="c.id" class="source-button"
          :class="{ selected: activeChannel === c.id && view === 'messages' }" @click="openChannel(c)">
          <component :is="kindIcons[c.kind] || FolderOpen" :size="15" />
          <span class="source-name" :title="c.name">{{ c.name }}</span>
          <small>{{ fmt(c.message_count) }}</small>
        </button>
        <div v-if="!filteredChannels.length" class="sidebar-empty">暂无可浏览的来源</div>
      </div>
      <div class="side-footer">
        <div class="online-dot"></div>
        <div><strong>仅本地运行</strong><small>127.0.0.1 · 数据不自动上传</small></div>
        <ShieldCheck :size="17" />
      </div>
    </aside>

    <main class="main">
      <header class="topbar">
        <div class="topbar-left">
          <button class="mobile-menu-button icon-button" @click="mobileMenu = true" aria-label="展开导航"><Menu :size="21" /></button>
          <span class="breadcrumb-muted">WORKSPACE</span><ChevronRight :size="14" class="breadcrumb-muted" />
          <span class="breadcrumb-active">{{ viewTitle }}</span>
        </div>
        <div class="topbar-actions">
          <span class="connection-indicator"><span></span> LOCAL SERVICE</span>
          <button class="icon-button" title="刷新" :disabled="loading" @click="refresh"><RefreshCw :size="17" :class="{ spinning: loading }"/></button>
          <button class="btn btn-primary btn-small" @click="goto('import')"><UploadCloud :size="16" />导入记录</button>
        </div>
      </header>

      <div class="content">
        <div v-if="errorDetail" class="alert alert-danger"><AlertCircle :size="17"/> {{ errorDetail }}</div>
        <template v-if="view === 'overview'">
          <div class="hero">
            <div class="hero-content">
              <div class="eyebrow"><span class="sparkle-point"></span> YOUR PERSONAL MEMORY SYSTEM</div>
              <h1>让每一次讨论，<br><span>成为可复用的知识。</span></h1>
              <p>将分散在 Discord 服务器、帖子和私信中的发言整理归档，借助 AI 发现值得留下的想法、决定和线索。</p>
              <div class="hero-actions">
                <button class="btn btn-primary" @click="goto('ai')"><Sparkles :size="17"/>开始智能总结<ArrowRight :size="16"/></button>
                <button class="btn btn-secondary" @click="goto('messages')">浏览历史消息</button>
              </div>
            </div>
            <div class="hero-decoration" aria-hidden="true">
              <div class="orbit orbit-one"></div><div class="orbit orbit-two"></div>
              <div class="orb-glow"><Database :size="66" :stroke-width="1.1" /></div>
            </div>
          </div>
          <div class="stat-grid">
            <div class="stat-card"><div class="stat-top"><span>归档消息</span><MessagesSquare :size="20"/></div>
              <strong>{{ fmt(stats.messages) }}</strong><small>来自自己的历史发言</small></div>
            <div class="stat-card"><div class="stat-top"><span>会话来源</span><FolderOpen :size="20"/></div>
              <strong>{{ fmt(stats.channels) }}</strong><small>频道 · 帖子 · 私信</small></div>
            <div class="stat-card"><div class="stat-top"><span>AI 知识摘要</span><Sparkles :size="20"/></div>
              <strong>{{ fmt(stats.summaries) }}</strong><small>可追溯到原始消息</small></div>
          </div>
          <div class="dashboard-grid">
            <section class="panel">
              <div class="panel-title-row"><div><h2>消息来源分布</h2><p>按会话类型自动分类</p></div><Activity :size="18" class="muted-icon"/></div>
              <div v-if="kindEntries.length" class="kind-list">
                <div v-for="[kind, count] in kindEntries" :key="kind" class="kind-line">
                  <div class="kind-label"><component :is="kindIcons[kind] || FolderOpen" :size="16"/><span>{{ kindLabels[kind] || kind }}</span></div>
                  <div class="kind-track"><div :style="{ width: Math.max(2, count / (stats.messages || 1) * 100) + '%' }"></div></div>
                  <strong>{{ fmt(count) }}</strong>
                </div>
              </div>
              <div v-else class="empty-small"><Inbox :size="24" />导入数据后，这里将显示消息来源分布。</div>
            </section>
            <section class="panel">
              <div class="panel-title-row"><div><h2>最近生成的知识</h2><p>AI 提炼的重要内容</p></div><button class="text-action" @click="goto('summaries')">查看全部 <ArrowRight :size="14"/></button></div>
              <div v-if="summaries.length" class="recent-list">
                <button v-for="s in summaries.slice(0, 4)" :key="s.id" class="recent-item" @click="summaryOpen(s)">
                  <div class="recent-icon"><BookOpen :size="17"/></div>
                  <div><strong>{{ s.title }}</strong><small>{{ fmt(s.message_count) }} 条消息 · {{ compactDate(s.created_at) }}</small></div>
                  <ChevronRight :size="16"/>
                </button>
              </div>
              <div v-else class="empty-small"><Sparkles :size="25"/>还没有知识摘要。完成消息导入后即可生成。</div>
            </section>
          </div>
          <section class="panel latest-panel">
            <div class="panel-title-row"><div><h2>最近归档的消息</h2><p>保留原始文本与时间信息</p></div><button class="text-action" @click="goto('messages')">消息浏览器 <ArrowRight :size="14"/></button></div>
            <div v-if="featuredMessages.length" class="mini-message-list">
              <div v-for="m in featuredMessages" :key="m.id" class="mini-message">
                <div class="mini-message-meta"><Hash :size="14"/> {{ m.channel_name }} <span>· {{ date(m.timestamp) }}</span></div>
                <p>{{ m.content || '（仅含附件的消息）' }}</p>
              </div>
            </div>
            <div v-else class="empty-small"><Inbox :size="24"/>知识库还是空的，先导入你的 Discord 历史记录吧。</div>
          </section>
        </template>

        <template v-else-if="view === 'messages'">
          <div class="page-heading"><div class="eyebrow">MESSAGE EXPLORER</div><h1>历史消息浏览器</h1>
            <p>{{ currentChannel ? ('当前来源 · ' + currentChannel.name) : '跨频道搜索自己的 Discord 历史发言' }}</p></div>
          <div class="toolbar-card">
            <label class="search-field"><Search :size="18"/><input v-model="messageQuery" @input="searchMessages" placeholder="搜索正文、频道名或消息 ID..."/></label>
            <div class="filter-chip"><Filter :size="15"/> {{ currentChannel?.name || '全部来源' }}</div>
            <button v-if="activeChannel" class="btn btn-light" @click="clearChannel"><X :size="14"/>清除筛选</button>
          </div>
          <div class="list-meta"><span>找到 <strong>{{ fmt(messages.total) }}</strong> 条历史消息</span><span>按照发送时间排序</span></div>
          <div v-if="messages.items.length" class="message-cards">
            <article v-for="m in messages.items" :key="m.id" class="message-card">
              <div class="message-head">
                <div class="message-avatar"><Hash :size="18"/></div>
                <div class="message-byline"><strong>{{ m.channel_name }}</strong><span>{{ m.guild_name || kindLabels[m.kind] || 'Discord' }}</span></div>
                <time>{{ date(m.timestamp) }}</time>
                <a :href="messageLink(m)" target="_blank" rel="noopener noreferrer" title="定位到 Discord 原消息" class="icon-button subtle-link"><ArrowUpRight :size="18"/></a>
              </div>
              <div class="message-body">{{ m.content || '（仅含附件的消息）' }}</div>
              <div v-if="m.attachments?.length" class="attachment-row">
                <a v-for="(a, index) in m.attachments" :key="index" v-show="safeLink(a.url)" :href="safeLink(a.url)" target="_blank" rel="noopener noreferrer">
                  <Link2 :size="13"/>{{ a.filename || '附件链接' }}
                </a>
              </div>
              <div class="message-foot"><span>ID {{ m.id }}</span><span v-if="m.pinned === 1" class="pin-label">已置顶</span><span>{{ m.source }}</span></div>
            </article>
          </div>
          <div v-else class="empty-block"><Search :size="30"/><h3>没有找到消息</h3><p>更换关键词或导入新的消息归档。</p></div>
          <div v-if="messages.total > messages.limit" class="pagination">
            <span>第 {{ Math.floor(messages.offset / messages.limit) + 1 }} / {{ Math.ceil(messages.total / messages.limit) }} 页</span>
            <div><button class="icon-button" :disabled="messages.offset === 0" @click="page(-1)"><ChevronLeft :size="18"/></button>
              <button class="icon-button" :disabled="messages.offset + messages.limit >= messages.total" @click="page(1)"><ChevronRight :size="18"/></button></div>
          </div>
        </template>

        <template v-else-if="view === 'summaries'">
          <div class="page-heading split-heading"><div><div class="eyebrow">KNOWLEDGE COLLECTION</div><h1>知识摘要</h1><p>从历史发言中提炼的主题、决定、待办与知识</p></div>
            <button class="btn btn-primary" @click="goto('ai')"><Sparkles :size="17"/>生成新摘要</button></div>
          <div v-if="summaries.length" class="summary-layout">
            <div class="summary-list">
              <button v-for="s in summaries" :key="s.id" class="summary-list-item" :class="{ active: selectedSummary?.id === s.id }" @click="selectedSummary = s">
                <div class="summary-list-icon"><BookOpen :size="19"/></div>
                <div><strong>{{ s.title }}</strong><small>{{ date(s.created_at) }}</small><span>{{ fmt(s.message_count) }} 条来源消息</span></div>
              </button>
            </div>
            <article v-if="selectedSummary" class="summary-document">
              <div class="document-top"><span class="eyebrow">AI KNOWLEDGE NOTE</span>
                <button class="btn btn-light" @click="downloadSummary(selectedSummary)"><Download :size="16"/>Markdown</button></div>
              <h2>{{ selectedSummary.title }}</h2>
              <div class="document-metadata"><span><Sparkles :size="14"/>{{ selectedSummary.provider }} / {{ selectedSummary.model }}</span><span><MessagesSquare :size="14"/>{{ fmt(selectedSummary.message_count) }} 条</span></div>
              <div class="document-content">{{ selectedSummary.content }}</div>
              <div class="document-footer"><ShieldCheck :size="15"/> 摘要仅基于归档中的发言，请结合消息原文核验重要事实。</div>
            </article>
          </div>
          <div v-else class="empty-block"><BookOpen :size="34"/><h3>尚无知识摘要</h3><p>先导入数据，然后前往 AI 工作台生成第一份报告。</p>
            <button class="btn btn-primary" @click="goto('ai')">打开 AI 工作台 <ArrowRight :size="16"/></button></div>
        </template>

        <template v-else-if="view === 'ai'">
          <div class="page-heading"><div class="eyebrow">AI ANALYSIS STUDIO</div><h1>AI 知识分析工作台</h1><p>选择本地 Ollama 或兼容云端 API，分层总结大量历史消息。</p></div>
          <div class="studio-layout">
            <form class="panel ai-form" @submit.prevent="startSummary">
              <div class="form-section-title"><span class="section-step">01</span><div><h2>分析范围</h2><p>确定需要总结的消息来源</p></div></div>
              <div class="segmented">
                <button type="button" :class="{ active: aiScope === 'channel' }" @click="aiScope = 'channel'">指定会话</button>
                <button type="button" :class="{ active: aiScope === 'all' }" @click="aiScope = 'all'">所有归档</button>
              </div>
              <label v-if="aiScope === 'channel'" class="field"><span>选择频道 / 私信</span><select v-model="aiChannel" required>
                <option v-for="c in channels" :key="c.id" :value="c.id">{{ c.name }} ({{ fmt(c.message_count) }})</option>
              </select></label>
              <label class="field"><span>报告标题（可选）</span><input v-model="aiTitle" placeholder="例如：红石计算机技术讨论总结"/></label>
              <div class="form-divider"></div>
              <div class="form-section-title"><span class="section-step">02</span><div><h2>AI 引擎</h2><p>两种方式均由本地服务统一调用</p></div></div>
              <div class="provider-options">
                <button type="button" class="provider-option" :class="{ active: aiProvider === 'ollama' }" @click="aiProvider = 'ollama'"><HardDrive :size="23"/><strong>本地 Ollama</strong><small>内容留在本机</small></button>
                <button type="button" class="provider-option" :class="{ active: aiProvider === 'openai' }" @click="aiProvider = 'openai'"><Cloud :size="23"/><strong>兼容云端 API</strong><small>按需上传所选发言</small></button>
              </div>
              <label class="field"><span>服务端点</span><input v-model="aiEndpoint" required placeholder="http://127.0.0.1:11434"/></label>
              <label class="field"><span>模型名称</span><input v-model="aiModel" required placeholder="模型 ID"/></label>
              <label v-if="aiProvider === 'openai'" class="field"><span>API Key <small>仅本次任务使用，不保存</small></span><input v-model="aiKey" type="password" autocomplete="off" placeholder="sk-..."/></label>
              <button class="btn btn-primary analyze-button" type="submit" :disabled="aiRunning || !stats.messages">
                <LoaderCircle v-if="aiRunning" :size="17" class="spinning"/><Sparkles v-else :size="17"/>
                {{ aiRunning ? '分析正在进行中' : '生成知识摘要' }} <ArrowRight :size="16"/>
              </button>
              <p class="form-note"><LockKeyhole :size="14"/> 云端模式仅在你主动点击运行后发送本次所选消息。</p>
            </form>
            <div class="studio-side">
              <section class="panel analysis-state">
                <div class="panel-title-row"><div><h2>任务状态</h2><p>分批提炼、逐层合并</p></div><Activity :size="19" class="muted-icon"/></div>
                <div v-if="job" class="job-body">
                  <div class="job-status-icon" :class="job.status">
                    <CheckCircle2 v-if="job.status === 'complete'" :size="24"/>
                    <AlertCircle v-else-if="job.status === 'failed'" :size="24"/>
                    <LoaderCircle v-else :size="24" class="spinning"/>
                  </div>
                  <strong>{{ job.status === 'complete' ? '分析完成' : job.status === 'failed' ? '分析中断' : '正在分析消息' }}</strong>
                  <p>{{ job.detail }}</p>
                  <div class="job-progress"><div :style="{ width: job.total ? Math.min(100, Math.round(job.done / job.total * 100)) + '%' : '8%' }"></div></div>
                  <small>{{ job.total ? `${job.done} / ${job.total} 个处理单元` : '正在准备任务...' }}</small>
                  <button v-if="job.status === 'complete'" class="btn btn-secondary" @click="goto('summaries')">查看生成的摘要 <ArrowRight :size="15"/></button>
                </div>
                <div v-else class="empty-small"><Sparkles :size="26"/>准备好后，选择模型并开始分析。</div>
              </section>
              <section class="info-card">
                <div class="info-heading"><ShieldCheck :size="21"/><strong>本地优先与安全边界</strong></div>
                <p>归档消息保存在本机 SQLite 中。Ollama 默认连接回环地址，不会将内容发送给云端；云端 API 会收到你选择分析的消息文本。</p>
              </section>
              <section class="info-card blue-info">
                <div class="info-heading"><Layers3 :size="21"/><strong>适合长对话的处理方式</strong></div>
                <p>每组消息提取核心事实和消息 ID，再层层整合。官方数据包只包含自己的发言，因此 AI 会明确保留上下文缺失的不确定性。</p>
              </section>
            </div>
          </div>
        </template>

        <template v-else-if="view === 'import'">
          <div class="page-heading"><div class="eyebrow">DATA SOURCES & CONNECTIONS</div><h1>数据导入与同步</h1>
            <p>支持官方个人数据包、原插件预览 JSON，以及可选的只读在线扫描扩展。</p></div>
          <div class="import-grid">
            <section class="panel import-panel">
              <div class="import-icon"><FileArchive :size="28"/></div><h2>导入 Discord 历史记录</h2>
              <p>拖放 Discord 官方数据包 ZIP，或原版清理插件导出的预览 JSON。系统只读取消息，不读取账号支付、会话和其他敏感资料。</p>
              <div class="drop-zone" @dragover.prevent @drop.prevent="fileDropped">
                <UploadCloud :size="32"/><strong>{{ busyImport ? '正在解析、去重和入库...' : '拖动 ZIP / JSON 文件到这里' }}</strong>
                <span>或点击下方按钮选择文件</span>
                <label class="btn btn-primary" :class="{ disabled: busyImport }">
                  <input type="file" accept=".zip,.json" :disabled="busyImport" hidden @change="fileChanged"/>
                  <LoaderCircle v-if="busyImport" :size="16" class="spinning"/><FolderOpen v-else :size="16"/>选择归档文件
                </label>
              </div>
              <div v-if="importResult" class="import-success"><CheckCircle2 :size="18"/>
                新增 {{ fmt(importResult.added) }} 条 · 更新 {{ fmt(importResult.updated) }} 条 · 发现 {{ fmt(importResult.channels_found) }} 个来源</div>
              <div class="import-hint"><ShieldCheck :size="17"/>不会修改 Discord 上的消息，也不需要你的账号 Token。</div>
              <a class="official-link" href="https://support.discord.com/hc/en-us/articles/360004957991-Your-Discord-Data-Package" target="_blank" rel="noopener noreferrer">
                如何申请 Discord 官方数据包？<ArrowUpRight :size="15"/>
              </a>
            </section>
            <section class="panel connect-panel">
              <div class="connect-label"><div class="connect-icon"><Link2 :size="22"/></div><span class="tag-warning">可选 · 有账号风险</span></div>
              <h2>只读在线扫描扩展</h2>
              <p>需要用户主动安装配套 Chrome 扩展，在 Discord 网页端发起读取。扩展仅扫描自己发送的消息，不执行删除；Discord 仍禁止普通账号 self-bot 自动化。</p>
              <div class="pairing">
                <div class="pairing-top"><span><KeyRound :size="15"/>本地服务配对码</span><small>{{ pairing.expires }}</small></div>
                <div class="pairing-value"><code>{{ pairing.key || '等待本地服务...' }}</code><button class="icon-button" title="复制" @click="copyPairing"><Copy :size="17"/></button></div>
                <span class="pairing-help">将配对码填入浏览器扩展。Discord Token 不会发送到本地服务。</span>
              </div>
              <div class="setup-steps">
                <div><span>1</span>Chrome 扩展管理页启用开发者模式</div>
                <div><span>2</span>加载项目中的 <code>extension</code> 文件夹</div>
                <div><span>3</span>在 Discord 网页打开扩展并填写配对码</div>
                <div><span>4</span>选择具体频道或服务器并开始只读扫描</div>
              </div>
              <div class="risk-note"><ShieldAlert :size="19"/><span>平台风险无法通过请求限速完全消除。建议优先使用官方数据包，不要在重要账号上直接进行大量扫描。</span></div>
            </section>
          </div>
          <section class="panel privacy-panel"><div><LockKeyhole :size="20"/><h3>个人数据仅归你所有</h3></div>
            <p>服务只监听 127.0.0.1，归档文件保存在本机 data 目录。导出的聊天记录和摘要可能包含敏感信息，备份和共享时请自行加密。</p></section>
        </template>
      </div>
    </main>
    <div v-if="toast.message" class="toast" :class="toast.tone">
      <CheckCircle2 v-if="toast.tone === 'success'" :size="18"/><AlertCircle v-else :size="18"/>
      <span>{{ toast.message }}</span><button @click="toast.message = ''"><X :size="14"/></button>
    </div>
  </div>
</template>
