/* Read-only optional connector.
 * Important: Discord prohibits self-bots. No delete endpoint is implemented.
 * A user's Discord token is used ONLY for requests to discord.com/api/v10.
 * Only archived message data is sent to http://127.0.0.1:8765.
 */
'use strict';

const API_BASE = 'https://discord.com/api/v10';
const LOCAL_COLLECTOR = 'http://127.0.0.1:8765/api/collector';
const ID = /^\d{15,25}$/;
const DISCORD_EPOCH = 1420070400000n;
const tasks = new Map();

function readPageToken() {
  try {
    let token = null;
    const chunks = window.webpackChunkdiscord_app;
    if (Array.isArray(chunks)) {
      const packet = [[`dpa-${Date.now()}`], {}, req => {
        for (const id of Object.keys(req.c || {})) {
          try {
            const exported = req.c[id]?.exports;
            for (const item of [exported, exported?.default, ...Object.values(exported || {})]) {
              if (item && typeof item.getToken === 'function') {
                const value = item.getToken();
                if (typeof value === 'string' && value.length > 20) {
                  token = value;
                  return;
                }
              }
            }
          } catch (_) { /* unrelated modules */ }
        }
      }];
      try { chunks.push(packet); }
      finally {
        const index = chunks.lastIndexOf(packet);
        if (index >= 0) chunks.splice(index, 1);
      }
    }
    if (!token) {
      const value = window.localStorage.getItem('token');
      if (value) token = value.replace(/^"|"$/g, '');
    }
    return typeof token === 'string' && token.length >= 20 && token.length <= 4096 ? token : null;
  } catch (_) { return null; }
}

function fail(message) { throw new Error(message); }
function snowflake(ms) {
  const normalized = Math.max(Number(DISCORD_EPOCH), Math.floor(ms));
  return String((BigInt(normalized) - DISCORD_EPOCH) << 22n);
}
function update(task, extra) {
  Object.assign(task.status, extra);
}
function check(task) {
  if (task.controller.signal.aborted) fail('用户已停止任务。');
}
async function delay(ms, task) {
  check(task);
  await new Promise((resolve, reject) => {
    const abort = () => { clearTimeout(timer); reject(new Error('用户已停止任务。')); };
    const timer = setTimeout(() => {
      task.controller.signal.removeEventListener('abort', abort);
      resolve();
    }, ms);
    task.controller.signal.addEventListener('abort', abort, { once: true });
  });
  check(task);
}
async function requestApi(path, token, task) {
  for (let attempt = 0; attempt < 6; attempt++) {
    check(task);
    let response;
    try {
      response = await fetch(API_BASE + path, {
        method: 'GET', headers: { Authorization: token },
        credentials: 'omit', cache: 'no-store', redirect: 'error',
        signal: task.controller.signal,
      });
    } catch (error) {
      if (task.controller.signal.aborted) throw error;
      if (attempt === 5) fail('网络连接失败，在线采集已停止。');
      await delay(1200 * (attempt + 1), task);
      continue;
    }
    const body = await response.json().catch(() => null);
    if (response.status === 429 || response.status === 202) {
      if (attempt === 5) fail('Discord 限速或历史索引尚未就绪，已停止本轮。');
      const wait = Number(body?.retry_after);
      await delay(Number.isFinite(wait) && wait >= 0 ? wait * 1000 + 600 : 1500 * (attempt + 1), task);
      continue;
    }
    if (response.status === 401 || response.status === 403) fail(`Discord 访问受限（HTTP ${response.status}）。`);
    if (!response.ok) fail(`Discord 请求失败（HTTP ${response.status}）。`);
    return body;
  }
}
async function postLocal(task, channels, records) {
  check(task);
  const response = await fetch(LOCAL_COLLECTOR, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Archive-Pairing': task.pairing },
    body: JSON.stringify({ channels, messages: records }),
    cache: 'no-store', credentials: 'omit', redirect: 'error',
    signal: task.controller.signal,
  });
  if (!response.ok) fail(`本地服务同步失败（HTTP ${response.status}）。请检查配对码与服务状态。`);
  const result = await response.json();
  task.status.saved += Number(result.added || 0);
  task.status.updated += Number(result.updated || 0);
}
function channelKind(ch) {
  if (ch.type === 1) return 'dm';
  if (ch.type === 3) return 'group_dm';
  if ([10, 11, 12].includes(ch.type)) return 'thread';
  return ch.guild_id ? 'guild' : 'unknown';
}
function normalizeMessage(m) {
  return {
    id: String(m.id),
    channel_id: String(m.channel_id),
    timestamp: m.timestamp || '',
    content: m.content || '',
    pinned: typeof m.pinned === 'boolean' ? m.pinned : null,
    attachments: (m.attachments || []).map(a => ({
      id: a.id, filename: a.filename, url: a.url, size: a.size,
      description: a.description,
    })),
    metadata: { edited_timestamp: m.edited_timestamp, type: m.type },
  };
}
async function scan(task) {
  const { guildId, channelId, after, before, maxMessages } = task.options;
  const scripts = await chrome.scripting.executeScript({
    target: { tabId: task.tabId }, world: 'MAIN', func: readPageToken,
  });
  const token = scripts?.[0]?.result;
  if (typeof token !== 'string' || token.length < 20) fail('无法从已登录的 Discord 页面读取登录状态。');
  const me = await requestApi('/users/@me', token, task);
  if (!ID.test(me?.id || '')) fail('无法确认当前账号身份。');
  update(task, { account: me.username || me.global_name || me.id, phase: '扫描中' });

  const lower = BigInt(snowflake(after)) > 0n ? BigInt(snowflake(after)) - 1n : 0n;
  let cursor = BigInt(snowflake(before + 1));
  const channels = new Map();
  const seen = new Set();
  async function describe(channel) {
    if (channels.has(channel)) return channels.get(channel);
    const ch = await requestApi(`/channels/${channel}`, token, task);
    if (ch?.id !== channel) fail('频道信息不匹配，已停止扫描。');
    if (guildId === '@me' ? (ch.guild_id || ![1, 3].includes(ch.type)) : ch.guild_id !== guildId) {
      fail('频道不属于选择的服务器或私信范围。');
    }
    if ([4, 15, 16].includes(ch.type)) fail('请选择文字频道或具体帖子。');
    const info = {
      id: channel, guild_id: ch.guild_id || null,
      guild_name: null, name: ch.name || '私信', kind: channelKind(ch),
      metadata: { type: ch.type, recipient_ids: (ch.recipients || []).map(u => u.id) },
    };
    channels.set(channel, info);
    return info;
  }
  if (channelId) await describe(channelId);
  while (cursor > lower + 1n) {
    check(task);
    let batch;
    if (channelId) {
      const params = new URLSearchParams({ before: String(cursor), limit: '100' });
      batch = await requestApi(`/channels/${channelId}/messages?${params}`, token, task);
      if (!Array.isArray(batch)) fail('频道消息格式异常，已停止。');
    } else {
      const params = new URLSearchParams({
        author_id: me.id, sort_by: 'timestamp', sort_order: 'desc', limit: '25',
        max_id: String(cursor), min_id: String(lower), include_nsfw: 'true',
      });
      const result = await requestApi(`/guilds/${guildId}/messages/search?${params}`, token, task);
      if (!Array.isArray(result?.messages) || !Number.isInteger(result.total_results)) fail('搜索格式异常。');
      if (result.doing_deep_historical_index) fail('服务器历史索引未完成。');
      batch = result.messages.flat().filter(m => m && m.author?.id === me.id && m.hit !== false);
      if (!batch.length && result.total_results > 0) fail('搜索索引返回不完整，已停止。');
    }
    if (!batch.length) break;
    if (batch.some(m => !ID.test(m.id || ''))) fail('包含无效消息 ID，已停止。');
    const inPage = batch.filter(m => BigInt(m.id) < cursor);
    if (!inPage.length) fail('分页没有前进，已停止。');
    const next = inPage.reduce((smallest, m) => BigInt(m.id) < smallest ? BigInt(m.id) : smallest, cursor);
    const own = inPage.filter(m => BigInt(m.id) > lower && m.author?.id === me.id && !seen.has(m.id));
    for (const m of own) {
      if (!ID.test(m.channel_id || '') || (channelId && m.channel_id !== channelId)) fail('消息频道不匹配。');
      seen.add(m.id);
    }
    const descriptors = [];
    for (const channel of new Set(own.map(m => m.channel_id))) descriptors.push(await describe(channel));
    for (let start = 0; start < own.length; start += 100) {
      const subset = own.slice(start, start + 100);
      const needed = descriptors.filter(d => subset.some(m => m.channel_id === d.id));
      await postLocal(task, needed, subset.map(normalizeMessage));
    }
    task.status.scanned += inPage.length;
    task.status.own += own.length;
    task.status.pages += 1;
    task.status.through = new Date(Number((next >> 22n) + DISCORD_EPOCH)).toISOString();
    cursor = next;
    if (task.status.own >= maxMessages) {
      update(task, { phase: 'partial', message: `达到本轮 ${maxMessages} 条上限；已保存扫描部分。` });
      return;
    }
    if (cursor <= lower) break;
    await delay(channelId ? 300 : 1200, task);
  }
  update(task, { phase: 'complete', message: '本次可访问范围已扫描完成。' });
}
async function startTask(message) {
  const { tabId, guildId, channelId, pairing, after, before, maxMessages } = message;
  const tab = await chrome.tabs.get(tabId);
  if (!tab.url?.startsWith('https://discord.com/channels/')) fail('请先打开 Discord 网页中的具体频道。');
  if (guildId !== '@me' && !ID.test(guildId || '')) fail('服务器 ID 格式不正确。');
  if (channelId && !ID.test(channelId)) fail('频道或帖子 ID 格式不正确。');
  if (guildId === '@me' && !channelId) fail('私信必须指定具体会话 ID。');
  if (!pairing || pairing.length < 16 || pairing.length > 100) fail('请填写本地 GUI 显示的配对码。');
  if (!Number.isFinite(after) || !Number.isFinite(before) || after > before) fail('时间范围无效。');
  if (!Number.isInteger(maxMessages) || maxMessages < 1 || maxMessages > 20000) fail('本轮上限须在 1 到 20000 条之间。');
  if (tasks.get(tabId)?.status.phase === 'running' || tasks.get(tabId)?.status.phase === '扫描中') fail('已有任务正在运行。');
  const task = {
    tabId, pairing, options: { guildId, channelId, after, before: Math.min(before, Date.now()), maxMessages },
    controller: new AbortController(),
    status: { phase: 'running', account: '', scanned: 0, own: 0, pages: 0, saved: 0, updated: 0, through: '', message: '' },
  };
  tasks.set(tabId, task);
  // Do not await: the popup gets its response immediately and can poll status.
  scan(task).catch(error => {
    update(task, {
      phase: task.controller.signal.aborted ? 'stopped' : 'failed',
      message: task.controller.signal.aborted ? '任务已停止；已经同步的内容仍保留。' : error.message,
    });
  }).finally(() => { task.pairing = ''; });
  return { started: true };
}
chrome.runtime.onMessage.addListener((message, sender, respond) => {
  if (sender.id !== chrome.runtime.id) return false;
  (async () => {
    if (message?.op === 'START') return startTask(message);
    if (message?.op === 'STATUS') return tasks.get(message.tabId)?.status ||
      { phase: 'idle', message: '暂无运行任务。服务工作进程重启后需重新扫描。' };
    if (message?.op === 'STOP') {
      const task = tasks.get(message.tabId);
      task?.controller.abort();
      return { stopped: !!task };
    }
    fail('不支持的操作。');
  })().then(result => respond({ ok: true, result }), error => respond({ ok: false, error: error.message }));
  return true;
});
chrome.tabs.onRemoved.addListener(tabId => tasks.get(tabId)?.controller.abort());
