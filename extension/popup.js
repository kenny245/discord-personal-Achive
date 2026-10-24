'use strict';
const $ = id => document.getElementById(id);
let activeTab = null;
const running = new Set(['running', '扫描中']);

async function tell(message) {
  const reply = await chrome.runtime.sendMessage(message);
  if (!reply?.ok) throw new Error(reply?.error || '扩展通信失败');
  return reply.result;
}
function showStatus(status) {
  $('phase').textContent = {
    idle: '准备就绪', running: '任务启动中', '扫描中': '正在扫描',
    complete: '本次扫描完成', partial: '部分扫描已完成',
    stopped: '扫描已停止', failed: '扫描失败',
  }[status.phase] || status.phase;
  $('account').textContent = status.account || '';
  $('message').textContent = status.message || '正在读取自己发送的历史消息，仅同步到本地。';
  $('scanned').textContent = Number(status.scanned || 0).toLocaleString();
  $('own').textContent = Number(status.own || 0).toLocaleString();
  $('saved').textContent = Number(status.saved || 0).toLocaleString();
  $('through').textContent = status.through ? '已扫到消息发送时间：' + status.through : '';
  $('stop').disabled = !running.has(status.phase);
  $('start').disabled = running.has(status.phase) || !$('risk').checked;
}
async function currentTab() {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  const tab = tabs[0];
  if (!tab?.id || !tab.url?.startsWith('https://discord.com/channels/')) throw new Error('请先在当前标签页打开 Discord 网页。');
  return tab;
}
function fillCurrent() {
  const match = activeTab?.url?.match(/^https:\/\/discord\.com\/channels\/(\d{15,25}|@me)\/(\d{15,25})/);
  if (!match) throw new Error('请打开具体频道或私信，再填入当前范围。');
  $('guild').value = match[1];
  $('channel').value = match[2];
}
async function poll() {
  if (!activeTab?.id) return;
  try { showStatus(await tell({ op: 'STATUS', tabId: activeTab.id })); }
  catch (error) { $('message').textContent = error.message; }
}
$('fill').addEventListener('click', () => {
  try { fillCurrent(); } catch (error) { $('message').textContent = error.message; }
});
$('risk').addEventListener('change', () => { $('start').disabled = !$('risk').checked; });
$('start').addEventListener('click', async () => {
  if (!$('risk').checked) return;
  $('start').disabled = true;
  try {
    activeTab = await currentTab();
    const after = $('after').value ? new Date($('after').value).getTime() : 1420070400000;
    const before = $('before').value ? new Date($('before').value).getTime() : Date.now();
    await tell({
      op: 'START', tabId: activeTab.id,
      guildId: $('guild').value.trim(), channelId: $('channel').value.trim(),
      pairing: $('pairing').value.trim(),
      after, before, maxMessages: Number($('limit').value),
    });
    $('pairing').value = ''; // No credential persistence.
    await poll();
  } catch (error) { $('phase').textContent = '无法启动'; $('message').textContent = error.message; $('start').disabled = false; }
});
$('stop').addEventListener('click', async () => {
  if (!activeTab) return;
  await tell({ op: 'STOP', tabId: activeTab.id });
  await poll();
});
(async () => {
  try {
    activeTab = await currentTab();
    try { fillCurrent(); } catch (_) { /* user may be at channel list */ }
    await poll();
    setInterval(poll, 1100);
  } catch (error) { $('message').textContent = error.message; }
})();
