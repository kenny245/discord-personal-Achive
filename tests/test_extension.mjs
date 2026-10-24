// VM-based test: no real Discord credentials, HTTP calls, or browser tabs.
import assert from 'node:assert/strict'
import fs from 'node:fs'
import vm from 'node:vm'

const code = fs.readFileSync(new URL('../extension/background.js', import.meta.url), 'utf8')
const guild = '223456789012345678'
const channel = '323456789012345678'
const me = '123456789012345678'
const ms = Date.now() - 90_000
const snowflake = String((BigInt(ms) - 1420070400000n) << 22n)
const own = {
  id: snowflake, channel_id: channel, author: { id: me }, pinned: false,
  content: '讨论 Python 归档', type: 0, attachments: [],
  timestamp: new Date(ms).toISOString(),
}
const other = { ...own, id: String(BigInt(snowflake) + 1n),
  author: { id: '423456789012345678' }, content: '其他人的内容' }
let listener = null
let pageCount = 0
const calls = []
const sandbox = {
  console, setTimeout, clearTimeout, AbortController, URLSearchParams, Date, BigInt,
  chrome: {
    runtime: {
      id: 'test-extension',
      onMessage: { addListener(fn) { listener = fn } },
    },
    tabs: {
      async get() { return { url: 'https://discord.com/channels/' + guild + '/' + channel } },
      onRemoved: { addListener() {} },
    },
    scripting: { async executeScript() { return [{ result: 'fake-token-for-unit-tests-only' }] } },
  },
  fetch: async (url, options) => {
    calls.push({ url, method: options.method, headers: options.headers, body: options.body })
    let status = 200, body
    if (url.endsWith('/users/@me')) body = { id: me, username: 'tester' }
    else if (url.endsWith('/channels/' + channel))
      body = { id: channel, guild_id: guild, name: 'general', type: 0 }
    else if (url.includes('/channels/' + channel + '/messages?'))
      body = pageCount++ === 0 ? [own, other] : []
    else if (url === 'http://127.0.0.1:8765/api/collector')
      body = { added: 1, updated: 0 }
    else throw new Error('Unexpected route: ' + url)
    return { ok: true, status, async json() { return body } }
  },
}
vm.runInNewContext(code, sandbox)
assert.ok(listener, 'Message handler not registered')
const send = message => new Promise(resolve => {
  listener(message, { id: 'test-extension' }, resolve)
})
const start = await send({
  op: 'START', tabId: 15, guildId: guild, channelId: channel,
  pairing: 'abcdefghijklmnopqrstuvwx',
  after: Date.now() - 300_000, before: Date.now(), maxMessages: 100,
})
assert.equal(start.ok, true, JSON.stringify(start))
let current
for (let i = 0; i < 30; i++) {
  await new Promise(resolve => setTimeout(resolve, 70))
  current = (await send({ op: 'STATUS', tabId: 15 })).result
  if (['complete', 'failed', 'partial'].includes(current.phase)) break
}
assert.equal(current.phase, 'complete', JSON.stringify(current))
assert.equal(current.own, 1)
assert.equal(current.saved, 1)
const outbound = calls.find(call => call.url.includes('/api/collector'))
assert.ok(outbound)
const sent = JSON.parse(outbound.body)
assert.equal(sent.messages.length, 1)
assert.equal(sent.messages[0].content, '讨论 Python 归档')
assert.equal(outbound.headers['X-Archive-Pairing'], 'abcdefghijklmnopqrstuvwx')
assert.ok(!outbound.body.includes('fake-token-for-unit-tests-only'))
assert.ok(calls.filter(x => x.url.startsWith('https://discord.com/')).every(x => x.method === 'GET'))
console.log('PASS: only own messages, Discord GET-only, no token in local sync, pagination')
