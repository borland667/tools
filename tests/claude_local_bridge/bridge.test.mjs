import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import http from 'node:http'
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import path from 'node:path'
import test from 'node:test'

const ROOT_DIR = path.resolve(import.meta.dirname, '../..')
const BRIDGE_SCRIPT = path.join(ROOT_DIR, 'claude_local_bridge', 'bridge.mjs')

test('aggregates providers, filters non-conversation models, and preserves duplicate route IDs', async t => {
  const upstreams = []
  t.after(async () => {
    await closeServers(upstreams)
  })

  const anthropic = await startAnthropicProvider({
    models: [
      model('shared-model'),
      model('anthropic-only'),
      model('Qwen3-Embedding-0.6B-4bit-DWQ'),
      model('VisualQuality-R1-7B-4bit'),
    ],
  })
  upstreams.push(anthropic.server)

  const openai = await startOpenAiProvider({
    models: [
      model('shared-model'),
      model('openai-only'),
      model('Qwen3-Reranker-0.6B-4bit'),
    ],
  })
  upstreams.push(openai.server)

  await withBridge(
    t,
    [
      provider('omlx', 'anthropic', anthropic.baseUrl),
      provider('lmstudio', 'openai', openai.baseUrl),
    ],
    async bridge => {
      const response = await getJson(`${bridge.baseUrl}/v1/models`)
      const ids = response.data.map(item => item.id)

      assert.deepEqual(ids.sort(), [
        'lmstudio/openai-only',
        'lmstudio/shared-model',
        'omlx/anthropic-only',
        'omlx/shared-model',
      ])
      assert.equal(ids.some(id => /embedding|reranker|visualquality/i.test(id)), false)
      assert.equal(response.data.find(item => item.id === 'omlx/shared-model').owned_by, 'omlx')
      assert.equal(response.data.find(item => item.id === 'lmstudio/shared-model').owned_by, 'lmstudio')
    },
  )
})

test('routes Anthropic and OpenAI-compatible message requests by provider-qualified model', async t => {
  const upstreams = []
  t.after(async () => {
    await closeServers(upstreams)
  })

  const anthropic = await startAnthropicProvider({
    models: [model('anthropic-chat')],
  })
  upstreams.push(anthropic.server)

  const openai = await startOpenAiProvider({
    models: [model('openai-chat')],
  })
  upstreams.push(openai.server)

  await withBridge(
    t,
    [
      provider('omlx', 'anthropic', anthropic.baseUrl),
      provider('lmstudio', 'openai', openai.baseUrl),
    ],
    async bridge => {
      const anthropicResponse = await postJson(`${bridge.baseUrl}/v1/messages`, {
        model: 'omlx/anthropic-chat',
        max_tokens: 16,
        messages: [{ role: 'user', content: 'hello anthropic' }],
      })

      assert.equal(anthropicResponse.model, 'anthropic-chat')
      assert.equal(anthropic.requests.messages.length, 1)
      assert.equal(anthropic.requests.messages[0].model, 'anthropic-chat')

      const openAiResponse = await postJson(`${bridge.baseUrl}/v1/messages`, {
        model: 'lmstudio/openai-chat',
        max_tokens: 16,
        messages: [{ role: 'user', content: 'hello openai' }],
      })

      assert.equal(openAiResponse.type, 'message')
      assert.deepEqual(openAiResponse.content, [
        { type: 'text', text: 'openai provider ok' },
      ])
      assert.equal(openai.requests.chatCompletions.length, 1)
      assert.equal(openai.requests.chatCompletions[0].model, 'openai-chat')
      assert.equal(openai.requests.chatCompletions[0].messages.at(-1).content, 'hello openai')
    },
  )
})

test('routes Anthropic-family tool requests to configured tool model', async t => {
  const upstreams = []
  t.after(async () => {
    await closeServers(upstreams)
  })

  const anthropic = await startAnthropicProvider({
    models: [model('general-chat')],
  })
  upstreams.push(anthropic.server)

  const openai = await startOpenAiProvider({
    models: [model('tool-chat')],
  })
  upstreams.push(openai.server)

  await withBridge(
    t,
    [
      provider('omlx', 'anthropic', anthropic.baseUrl),
      provider('lmstudio', 'openai', openai.baseUrl),
    ],
    async bridge => {
      await postJson(`${bridge.baseUrl}/v1/messages`, {
        model: 'claude-sonnet-4-5',
        max_tokens: 16,
        tools: [
          {
            name: 'lookup',
            description: 'look something up',
            input_schema: { type: 'object', properties: {} },
          },
        ],
        messages: [{ role: 'user', content: 'use a tool' }],
      })

      assert.equal(openai.requests.chatCompletions.length, 1)
      assert.equal(openai.requests.chatCompletions[0].model, 'tool-chat')
      assert.equal(openai.requests.chatCompletions[0].tools[0].function.name, 'lookup')
      assert.equal(anthropic.requests.messages.length, 0)
    },
    {
      env: {
        CLAUDE_LOCAL_TOOL_MODEL: 'lmstudio/tool-chat',
      },
    },
  )
})

test('isolates failed providers while keeping healthy provider models available', async t => {
  const upstreams = []
  t.after(async () => {
    await closeServers(upstreams)
  })

  const anthropic = await startAnthropicProvider({
    models: [model('healthy-chat')],
  })
  upstreams.push(anthropic.server)

  const failing = await startFailingProvider()
  upstreams.push(failing.server)

  await withBridge(
    t,
    [
      provider('omlx', 'anthropic', anthropic.baseUrl),
      provider('broken', 'openai', failing.baseUrl),
    ],
    async bridge => {
      const health = await getJson(`${bridge.baseUrl}/healthz`)
      assert.equal(health.providerCount, 2)
      assert.equal(health.models, 1)
      assert.equal(health.providers.find(item => item.id === 'omlx').ok, true)
      assert.equal(health.providers.find(item => item.id === 'broken').ok, false)

      const response = await getJson(`${bridge.baseUrl}/v1/models`)
      assert.deepEqual(response.data.map(item => item.id), ['omlx/healthy-chat'])
    },
  )
})

function model(id) {
  return {
    id,
    object: 'model',
    created: 0,
    owned_by: 'test',
  }
}

function provider(id, type, baseUrl) {
  return {
    id,
    type,
    baseUrl,
    authScheme: 'none',
    label: id,
  }
}

async function withBridge(t, providers, callback, options = {}) {
  const port = await getFreePort()
  const workDir = await mkdtemp(path.join(tmpdir(), 'claude-local-bridge-test-'))
  const providersFile = path.join(workDir, 'providers.json')
  const configFile = path.join(workDir, 'claude.json')
  const stdout = []
  const stderr = []

  await writeFile(providersFile, JSON.stringify({ providers }), 'utf8')

  const child = spawn(process.execPath, [BRIDGE_SCRIPT, 'serve'], {
    cwd: ROOT_DIR,
    env: {
      ...process.env,
      ...options.env,
      CLAUDE_LOCAL_BRIDGE_HOST: '127.0.0.1',
      CLAUDE_LOCAL_BRIDGE_PORT: String(port),
      CLAUDE_LOCAL_PROVIDERS_FILE: providersFile,
      CLAUDE_GLOBAL_CONFIG_FILE: configFile,
      CLAUDE_LOCAL_MODEL_SYNC_INTERVAL_MS: '60000',
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  })

  child.stdout.on('data', chunk => stdout.push(chunk.toString('utf8')))
  child.stderr.on('data', chunk => stderr.push(chunk.toString('utf8')))

  t.after(async () => {
    child.kill()
    await onceExit(child)
    await rm(workDir, { recursive: true, force: true })
  })

  try {
    await waitForHealth(`http://127.0.0.1:${port}/healthz`)
    await callback({
      baseUrl: `http://127.0.0.1:${port}`,
      configFile,
      get logs() {
        return stdout.join('') + stderr.join('')
      },
    })
  } catch (error) {
    error.message += `\n\nBridge logs:\n${stdout.join('')}${stderr.join('')}`
    throw error
  }
}

async function startAnthropicProvider({ models }) {
  const requests = { messages: [] }
  const server = http.createServer(async (req, res) => {
    if (req.method === 'GET' && ['/api/v1/models', '/v1/models'].includes(req.url)) {
      return writeJson(res, 200, { object: 'list', data: models })
    }

    if (req.method === 'POST' && req.url === '/v1/messages') {
      const body = await readJsonBody(req)
      requests.messages.push(body)
      return writeJson(res, 200, {
        id: 'msg_anthropic_test',
        type: 'message',
        role: 'assistant',
        model: body.model,
        content: [{ type: 'text', text: 'anthropic provider ok' }],
        stop_reason: 'end_turn',
        stop_sequence: null,
        usage: { input_tokens: 1, output_tokens: 3 },
      })
    }

    writeJson(res, 404, { error: `unexpected ${req.method} ${req.url}` })
  })

  const baseUrl = await listen(server)
  return { server, baseUrl, requests }
}

async function startOpenAiProvider({ models }) {
  const requests = { chatCompletions: [] }
  const server = http.createServer(async (req, res) => {
    if (req.method === 'GET' && ['/v1/models', '/api/v1/models'].includes(req.url)) {
      return writeJson(res, 200, { object: 'list', data: models })
    }

    if (req.method === 'POST' && req.url === '/v1/chat/completions') {
      const body = await readJsonBody(req)
      requests.chatCompletions.push(body)
      return writeJson(res, 200, {
        id: 'chatcmpl_test',
        object: 'chat.completion',
        created: 0,
        model: body.model,
        choices: [
          {
            index: 0,
            finish_reason: 'stop',
            message: {
              role: 'assistant',
              content: 'openai provider ok',
            },
          },
        ],
        usage: { prompt_tokens: 1, completion_tokens: 3, total_tokens: 4 },
      })
    }

    writeJson(res, 404, { error: `unexpected ${req.method} ${req.url}` })
  })

  const baseUrl = await listen(server)
  return { server, baseUrl, requests }
}

async function startFailingProvider() {
  const server = http.createServer((_req, res) => {
    writeJson(res, 500, { error: 'provider down' })
  })
  const baseUrl = await listen(server)
  return { server, baseUrl }
}

async function listen(server) {
  await new Promise((resolve, reject) => {
    server.once('error', reject)
    server.listen(0, '127.0.0.1', resolve)
  })
  const address = server.address()
  assert.equal(typeof address, 'object')
  return `http://127.0.0.1:${address.port}`
}

async function getFreePort() {
  const server = http.createServer()
  const baseUrl = await listen(server)
  await closeServers([server])
  return Number(new URL(baseUrl).port)
}

async function waitForHealth(url) {
  const deadline = Date.now() + 5000
  let lastError
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url)
      if (response.ok) {
        return
      }
      lastError = new Error(`HTTP ${response.status}`)
    } catch (error) {
      lastError = error
    }
    await new Promise(resolve => setTimeout(resolve, 100))
  }
  throw lastError ?? new Error(`timed out waiting for ${url}`)
}

async function getJson(url) {
  const response = await fetch(url)
  assert.equal(response.ok, true, `${url} returned HTTP ${response.status}`)
  return response.json()
}

async function postJson(url, body) {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  })
  assert.equal(response.ok, true, `${url} returned HTTP ${response.status}`)
  return response.json()
}

async function readJsonBody(req) {
  const chunks = []
  for await (const chunk of req) {
    chunks.push(chunk)
  }
  return JSON.parse(Buffer.concat(chunks).toString('utf8'))
}

function writeJson(res, status, payload) {
  res.writeHead(status, { 'content-type': 'application/json' })
  res.end(JSON.stringify(payload))
}

async function closeServers(servers) {
  await Promise.all(
    servers.map(server => new Promise(resolve => server.close(resolve))),
  )
}

async function onceExit(child) {
  if (child.exitCode !== null || child.signalCode !== null) {
    return
  }
  await new Promise(resolve => child.once('exit', resolve))
}
