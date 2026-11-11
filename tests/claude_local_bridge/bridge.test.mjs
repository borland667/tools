import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import http from 'node:http'
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import path from 'node:path'
import test from 'node:test'

const ROOT_DIR = path.resolve(import.meta.dirname, '../..')
const BRIDGE_SCRIPT = path.join(ROOT_DIR, 'claude_local_bridge', 'bridge.mjs')

test('aggregates all provider models and preserves duplicate route IDs', async t => {
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
      const rawRouteIds = ids.filter(id => id.includes('/'))

      assert.deepEqual(rawRouteIds.sort(), [
        'lmstudio/Qwen3-Reranker-0.6B-4bit',
        'lmstudio/openai-only',
        'lmstudio/shared-model',
        'omlx/Qwen3-Embedding-0.6B-4bit-DWQ',
        'omlx/VisualQuality-R1-7B-4bit',
        'omlx/anthropic-only',
        'omlx/shared-model',
      ])
      assert.equal(response.data.find(item => item.id === 'omlx/shared-model').owned_by, 'omlx')
      assert.equal(response.data.find(item => item.id === 'lmstudio/shared-model').owned_by, 'lmstudio')

      // autoClaudeDesktopAliases adds one Claude alias per conversation model
      // and skips embedding, reranker, and image-quality models.
      const aliases = response.data.filter(item => !item.id.includes('/'))
      assert.ok(aliases.every(item => item.id.startsWith('claude-')))
      assert.deepEqual(
        aliases.map(item => `${item.owned_by}/${item.upstream_model_id}`).sort(),
        [
          'lmstudio/openai-only',
          'lmstudio/shared-model',
          'omlx/anthropic-only',
          'omlx/shared-model',
        ],
      )
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

test('exposes Claude Desktop compatible aliases while routing to local models', async t => {
  const upstreams = []
  t.after(async () => {
    await closeServers(upstreams)
  })

  const anthropic = await startAnthropicProvider({
    models: [model('Qwen3.5-9b-Sushi-Coder-RL-MLX', { max_model_len: 262144 })],
  })
  upstreams.push(anthropic.server)

  await withBridge(
    t,
    [provider('omlx', 'anthropic', anthropic.baseUrl)],
    async bridge => {
      const models = await getJson(`${bridge.baseUrl}/v1/models`)
      assert.deepEqual(models.data.map(item => item.id).sort(), [
        'claude-sonnet-4-5',
        'omlx/Qwen3.5-9b-Sushi-Coder-RL-MLX',
      ])
      assert.equal(models.data.find(item => item.id === 'claude-sonnet-4-5').owned_by, 'omlx')
      assert.equal(
        models.data.find(item => item.id === 'claude-sonnet-4-5').max_model_len,
        262144,
      )
      assert.equal(
        models.data.find(item => item.id === 'omlx/Qwen3.5-9b-Sushi-Coder-RL-MLX')
          .max_model_len,
        262144,
      )

      const response = await postJson(`${bridge.baseUrl}/v1/messages`, {
        model: 'claude-sonnet-4-5',
        max_tokens: 16,
        messages: [{ role: 'user', content: 'hello alias' }],
      })

      assert.equal(response.model, 'Qwen3.5-9b-Sushi-Coder-RL-MLX')
      assert.equal(anthropic.requests.messages.length, 1)
      assert.equal(
        anthropic.requests.messages[0].model,
        'Qwen3.5-9b-Sushi-Coder-RL-MLX',
      )
    },
    {
      bridgeConfig: providersFile => ({
        ...bridgeConfig(providersFile, 'omlx/Qwen3.5-9b-Sushi-Coder-RL-MLX'),
        claudeDesktopModels: [
          {
            name: 'claude-sonnet-4-5',
            target: 'omlx/Qwen3.5-9b-Sushi-Coder-RL-MLX',
            labelOverride: 'Qwen3.5 Sushi Coder 9B via Local Bridge',
            anthropicFamilyTier: 'sonnet',
            isFamilyDefault: true,
          },
        ],
      }),
    },
  )
})

test('adds Claude Desktop aliases without hiding raw provider models', async t => {
  const upstreams = []
  t.after(async () => {
    await closeServers(upstreams)
  })

  const anthropic = await startAnthropicProvider({
    models: [
      model('Qwen3.5-9b-Sushi-Coder-RL-MLX'),
      model('Qwen3-Embedding-0.6B-4bit-DWQ'),
    ],
  })
  upstreams.push(anthropic.server)

  await withBridge(
    t,
    [provider('omlx', 'anthropic', anthropic.baseUrl)],
    async bridge => {
      const models = await getJson(`${bridge.baseUrl}/v1/models`)
      const ids = models.data.map(item => item.id).sort()

      assert.deepEqual(ids, [
        'claude-sonnet-4-5',
        'omlx/Qwen3-Embedding-0.6B-4bit-DWQ',
        'omlx/Qwen3.5-9b-Sushi-Coder-RL-MLX',
      ])
    },
    {
      bridgeConfig: providersFile => ({
        ...bridgeConfig(providersFile, 'claude-sonnet-4-5'),
        claudeDesktopModels: [
          {
            name: 'claude-sonnet-4-5',
            target: 'omlx/Qwen3.5-9b-Sushi-Coder-RL-MLX',
            labelOverride: 'Claude-facing local coder alias',
          },
        ],
      }),
    },
  )
})

test('keeps automatic Claude alias names stable when other models change', async t => {
  const upstreams = []
  t.after(async () => {
    await closeServers(upstreams)
  })

  const models = [model('stable-chat'), model('other-chat')]
  const anthropic = await startAnthropicProvider({ models })
  upstreams.push(anthropic.server)

  await withBridge(
    t,
    [provider('omlx', 'anthropic', anthropic.baseUrl)],
    async bridge => {
      const aliasFor = async upstreamModelId => {
        const response = await getJson(`${bridge.baseUrl}/v1/models`)
        return response.data.find(
          item => !item.id.includes('/') && item.upstream_model_id === upstreamModelId,
        )?.id
      }

      const before = await aliasFor('stable-chat')
      assert.match(before, /^claude-(opus|sonnet|haiku)-5-\d{6}$/)

      // Drop a model and add ones that sort before and after the stable one.
      models.splice(0, models.length, model('aaa-new-chat'), model('stable-chat'), model('zzz-new-chat'))
      await getJson(`${bridge.baseUrl}/sync-models`)

      assert.equal(await aliasFor('aaa-new-chat') !== undefined, true)
      assert.equal(await aliasFor('stable-chat'), before)

      const response = await postJson(`${bridge.baseUrl}/v1/messages`, {
        model: before,
        max_tokens: 16,
        messages: [{ role: 'user', content: 'hello' }],
      })
      assert.equal(response.model, 'stable-chat')
      assert.equal(anthropic.requests.messages.at(-1).model, 'stable-chat')
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

test('keeps tool requests on the selected route when it is tool capable', async t => {
  const upstreams = []
  t.after(async () => {
    await closeServers(upstreams)
  })

  const anthropic = await startAnthropicProvider({
    models: [
      model('Qwen3.5-9b-Sushi-Coder-RL-MLX'),
      model('Qwen3.6-27B-Heretic-MLX-bf16'),
    ],
  })
  upstreams.push(anthropic.server)

  await withBridge(
    t,
    [provider('omlx', 'anthropic', anthropic.baseUrl)],
    async bridge => {
      await postJson(`${bridge.baseUrl}/v1/messages`, {
        model: 'claude-sonnet-4-6',
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

      assert.equal(anthropic.requests.messages.length, 1)
      assert.equal(
        anthropic.requests.messages[0].model,
        'Qwen3.6-27B-Heretic-MLX-bf16',
      )
    },
    {
      bridgeConfig: providersFile => ({
        ...bridgeConfig(providersFile, 'claude-sonnet-4-5'),
        models: {
          main: 'claude-sonnet-4-5',
          small: 'claude-sonnet-4-5',
          tool: 'claude-sonnet-4-5',
        },
        claudeDesktopModels: [
          {
            name: 'claude-sonnet-4-5',
            target: 'omlx/Qwen3.5-9b-Sushi-Coder-RL-MLX',
            labelOverride: 'Fallback tool alias',
            toolCapable: true,
          },
          {
            name: 'claude-sonnet-4-6',
            target: 'omlx/Qwen3.6-27B-Heretic-MLX-bf16',
            labelOverride: 'Selected tool-capable alias',
            toolCapable: true,
          },
        ],
      }),
    },
  )
})

test('routes Anthropic-family image requests to configured vision model', async t => {
  const upstreams = []
  t.after(async () => {
    await closeServers(upstreams)
  })

  const anthropic = await startAnthropicProvider({
    models: [
      model('Qwen3.6-35B-A3B-Claude-Opus-VL-grafted-MLX-8bit'),
      model('Qwen3-VL-4B-Instruct-4bit'),
    ],
  })
  upstreams.push(anthropic.server)

  await withBridge(
    t,
    [provider('omlx', 'anthropic', anthropic.baseUrl)],
    async bridge => {
      await postJson(`${bridge.baseUrl}/v1/messages`, {
        model: 'claude-opus-4-8',
        max_tokens: 16,
        messages: [
          {
            role: 'user',
            content: [
              {
                type: 'image',
                source: {
                  type: 'base64',
                  media_type: 'image/png',
                  data: 'abc123',
                },
              },
              { type: 'text', text: 'describe this image' },
            ],
          },
        ],
      })

      assert.equal(anthropic.requests.messages.length, 1)
      assert.equal(
        anthropic.requests.messages[0].model,
        'Qwen3-VL-4B-Instruct-4bit',
      )
    },
    {
      bridgeConfig: providersFile => ({
        ...bridgeConfig(providersFile, 'claude-opus-4-8'),
        models: {
          main: 'claude-opus-4-8',
          small: 'claude-haiku-4-5-20251001',
          tool: 'claude-sonnet-4-5',
          vision: 'claude-haiku-4-5-20251001',
        },
        claudeDesktopModels: [
          {
            name: 'claude-opus-4-8',
            target: 'omlx/Qwen3.6-35B-A3B-Claude-Opus-VL-grafted-MLX-8bit',
            labelOverride: 'Broken VLM alias',
          },
          {
            name: 'claude-haiku-4-5-20251001',
            target: 'omlx/Qwen3-VL-4B-Instruct-4bit',
            labelOverride: 'Working vision alias',
          },
        ],
      }),
    },
  )
})

test('keeps image requests on the selected route when it is vision capable', async t => {
  const upstreams = []
  t.after(async () => {
    await closeServers(upstreams)
  })

  const anthropic = await startAnthropicProvider({
    models: [
      model('Qwen3.6-27B-Heretic-MLX-bf16'),
      model('Qwen3-VL-4B-Instruct-4bit'),
    ],
  })
  upstreams.push(anthropic.server)

  await withBridge(
    t,
    [provider('omlx', 'anthropic', anthropic.baseUrl)],
    async bridge => {
      await postJson(`${bridge.baseUrl}/v1/messages`, {
        model: 'claude-sonnet-4-6',
        max_tokens: 16,
        messages: [
          {
            role: 'user',
            content: [
              {
                type: 'image',
                source: {
                  type: 'base64',
                  media_type: 'image/png',
                  data: 'abc123',
                },
              },
              { type: 'text', text: 'describe this image' },
            ],
          },
        ],
      })

      assert.equal(anthropic.requests.messages.length, 1)
      assert.equal(
        anthropic.requests.messages[0].model,
        'Qwen3.6-27B-Heretic-MLX-bf16',
      )
    },
    {
      bridgeConfig: providersFile => ({
        ...bridgeConfig(providersFile, 'claude-sonnet-4-6'),
        models: {
          main: 'claude-sonnet-4-6',
          small: 'claude-haiku-4-5-20251001',
          tool: 'claude-sonnet-4-5',
          vision: 'claude-haiku-4-5-20251001',
        },
        claudeDesktopModels: [
          {
            name: 'claude-sonnet-4-6',
            target: 'omlx/Qwen3.6-27B-Heretic-MLX-bf16',
            labelOverride: 'Vision-capable selected alias',
            visionCapable: true,
          },
          {
            name: 'claude-haiku-4-5-20251001',
            target: 'omlx/Qwen3-VL-4B-Instruct-4bit',
            labelOverride: 'Fallback vision alias',
          },
        ],
      }),
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
      // One raw route plus its auto-generated Claude alias.
      assert.equal(health.models, 2)
      assert.equal(health.providers.find(item => item.id === 'omlx').ok, true)
      assert.equal(health.providers.find(item => item.id === 'broken').ok, false)

      const response = await getJson(`${bridge.baseUrl}/v1/models`)
      assert.deepEqual(
        response.data.filter(item => item.id.includes('/')).map(item => item.id),
        ['omlx/healthy-chat'],
      )
      assert.ok(response.data.every(item => item.owned_by === 'omlx'))
      assert.deepEqual(
        response.data.map(item => item.upstream_model_id),
        ['healthy-chat', 'healthy-chat'],
      )
    },
  )
})

test('loads and reloads bridge JSON config from the working directory', async t => {
  const upstreams = []
  t.after(async () => {
    await closeServers(upstreams)
  })

  const anthropic = await startAnthropicProvider({
    models: [model('first-chat'), model('second-chat')],
  })
  upstreams.push(anthropic.server)

  await withBridge(
    t,
    [provider('omlx', 'anthropic', anthropic.baseUrl)],
    async bridge => {
      let health = await getJson(`${bridge.baseUrl}/healthz`)
      assert.equal(health.mainModel, 'omlx/first-chat')
      assert.equal(health.bridgeConfigSource, bridge.bridgeConfigFile)

      await writeFile(
        bridge.bridgeConfigFile,
        JSON.stringify(bridgeConfig(bridge.providersFile, 'omlx/second-chat')),
        'utf8',
      )

      await getJson(`${bridge.baseUrl}/sync-models`)
      health = await getJson(`${bridge.baseUrl}/healthz`)
      assert.equal(health.mainModel, 'omlx/second-chat')
    },
    {
      bridgeConfig: providersFile => bridgeConfig(providersFile, 'omlx/first-chat'),
    },
  )
})

test('prefers bridge JSON settings over legacy environment fallbacks', async t => {
  const upstreams = []
  t.after(async () => {
    await closeServers(upstreams)
  })

  const anthropic = await startAnthropicProvider({
    models: [model('json-chat'), model('env-chat')],
  })
  upstreams.push(anthropic.server)

  await withBridge(
    t,
    [provider('omlx', 'anthropic', anthropic.baseUrl)],
    async bridge => {
      const health = await getJson(`${bridge.baseUrl}/healthz`)
      assert.equal(health.mainModel, 'omlx/json-chat')
    },
    {
      bridgeConfig: providersFile => bridgeConfig(providersFile, 'omlx/json-chat'),
      env: {
        CLAUDE_LOCAL_MAIN_MODEL: 'omlx/env-chat',
      },
    },
  )
})

test('emits streaming message start before a slow upstream sends headers', async t => {
  const upstreams = []
  t.after(async () => {
    await closeServers(upstreams)
  })

  const anthropic = await startSlowAnthropicStreamingProvider({
    models: [model('slow-chat')],
    headerDelayMs: 1500,
  })
  upstreams.push(anthropic.server)

  await withBridge(
    t,
    [provider('omlx', 'anthropic', anthropic.baseUrl)],
    async bridge => {
      const startedAt = Date.now()
      const response = await fetch(`${bridge.baseUrl}/v1/messages`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          model: 'omlx/slow-chat',
          max_tokens: 16,
          stream: true,
          messages: [{ role: 'user', content: 'hello' }],
        }),
      })

      assert.equal(response.ok, true)
      assert.equal(response.headers.get('content-type'), 'text/event-stream; charset=utf-8')
      const firstChunk = await readFirstChunk(response)
      assert.match(firstChunk, /event: message_start/)
      assert.match(firstChunk, /msg_bridge_warmup_/)
      assert.equal(Date.now() - startedAt < 1000, true)
    },
  )
})

test('emits visible progress while upstream only sends thinking deltas', async t => {
  const upstreams = []
  t.after(async () => {
    await closeServers(upstreams)
  })

  const anthropic = await startThinkingOnlyAnthropicStreamingProvider({
    models: [model('slow-thinking-chat')],
  })
  upstreams.push(anthropic.server)

  await withBridge(
    t,
    [provider('omlx', 'anthropic', anthropic.baseUrl)],
    async bridge => {
      const response = await fetch(`${bridge.baseUrl}/v1/messages`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          model: 'omlx/slow-thinking-chat',
          max_tokens: 16,
          stream: true,
          messages: [{ role: 'user', content: 'think slowly' }],
        }),
      })

      assert.equal(response.ok, true)
      const text = await readChunksUntil(response, /_Local model: /)
      assert.match(text, /event: content_block_start/)
      assert.match(text, /_Local model: waiting .* for visible model output/)
      assert.doesNotMatch(text, /\*\*Local model status\*\*/)
      assert.doesNotMatch(text, /thinking_delta/)
    },
    {
      bridgeConfig: providersFile => ({
        ...bridgeConfig(providersFile, 'omlx/slow-thinking-chat'),
        streamingProgress: {
          enabled: true,
          delayMs: 25,
          intervalMs: 50,
        },
        thinking: {
          mode: 'suppress',
        },
      }),
    },
  )
})

test('passes upstream Anthropic thinking blocks through by default', async t => {
  const upstreams = []
  t.after(async () => {
    await closeServers(upstreams)
  })

  const anthropic = await startThinkingOnlyAnthropicStreamingProvider({
    models: [model('slow-thinking-chat')],
  })
  upstreams.push(anthropic.server)

  await withBridge(
    t,
    [provider('omlx', 'anthropic', anthropic.baseUrl)],
    async bridge => {
      const response = await fetch(`${bridge.baseUrl}/v1/messages`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          model: 'omlx/slow-thinking-chat',
          max_tokens: 16,
          stream: true,
          messages: [{ role: 'user', content: 'think visibly' }],
        }),
      })

      assert.equal(response.ok, true)
      const text = await response.text()
      assert.match(text, /"type":"thinking"/)
      assert.match(text, /"type":"thinking_delta"/)
      assert.match(text, /still thinking/)
      assert.doesNotMatch(text, /\*\*Local model status\*\*/)
    },
  )
})

test('keeps visible output indices contiguous after suppressing thinking', async t => {
  const upstreams = []
  t.after(async () => {
    await closeServers(upstreams)
  })

  const anthropic = await startThinkingThenTextAnthropicStreamingProvider({
    models: [model('slow-thinking-text-chat')],
  })
  upstreams.push(anthropic.server)

  await withBridge(
    t,
    [provider('omlx', 'anthropic', anthropic.baseUrl)],
    async bridge => {
      const response = await fetch(`${bridge.baseUrl}/v1/messages`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          model: 'omlx/slow-thinking-text-chat',
          max_tokens: 16,
          stream: true,
          messages: [{ role: 'user', content: 'think, then answer' }],
        }),
      })

      assert.equal(response.ok, true)
      const text = await response.text()
      assert.match(text, /"index":0/)
      assert.match(text, /_Local model: waiting .* for visible model output/)
      assert.doesNotMatch(text, /\*\*Local model status\*\*/)
      assert.match(text, /"index":1/)
      assert.match(text, /final answer/)
      assert.doesNotMatch(text, /"index":2/)
      assert.doesNotMatch(text, /thinking_delta/)
    },
    {
      bridgeConfig: providersFile => ({
        ...bridgeConfig(providersFile, 'omlx/slow-thinking-text-chat'),
        streamingProgress: {
          enabled: true,
          delayMs: 25,
          intervalMs: 50,
        },
        thinking: {
          mode: 'suppress',
        },
      }),
    },
  )
})

test('uses streaming request timeout for long-running streams', async t => {
  const upstreams = []
  t.after(async () => {
    await closeServers(upstreams)
  })

  const anthropic = await startThinkingThenTextAnthropicStreamingProvider({
    models: [model('slow-timeout-chat')],
  })
  upstreams.push(anthropic.server)

  await withBridge(
    t,
    [provider('omlx', 'anthropic', anthropic.baseUrl)],
    async bridge => {
      const response = await fetch(`${bridge.baseUrl}/v1/messages`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          model: 'omlx/slow-timeout-chat',
          max_tokens: 16,
          stream: true,
          messages: [{ role: 'user', content: 'finish after the normal timeout' }],
        }),
      })

      assert.equal(response.ok, true)
      const text = await response.text()
      assert.match(text, /final answer/)
      assert.doesNotMatch(bridge.logs, /aborted due to timeout/)
    },
    {
      bridgeConfig: providersFile => ({
        ...bridgeConfig(providersFile, 'omlx/slow-timeout-chat'),
        requestTimeoutMs: 20,
        streamRequestTimeoutMs: 1000,
        streamingProgress: {
          enabled: false,
        },
      }),
    },
  )
})

test('includes OMLX provider activity in visible progress', async t => {
  const upstreams = []
  t.after(async () => {
    await closeServers(upstreams)
  })

  const anthropic = await startThinkingOnlyAnthropicStreamingProvider({
    models: [model('Qwen3.6-27B-Heretic-MLX-bf16')],
    endDelayMs: 1500,
    activity: {
      active_models: {
        models: [
          {
            id: 'Qwen3.6-27B-Heretic-MLX-bf16',
            is_loading: false,
            active_requests: 2,
            waiting_requests: 0,
            waiting: [],
            prefilling: [
              {
                request_id: 'prefill-test',
                processed: 8192,
                total: 32768,
                speed: 64.4,
                eta: 382,
              },
            ],
            generating: [],
            actual_size_formatted: '51.26GB',
          },
        ],
        memory_pressure: {
          enabled: true,
          current_formatted: '70.0GB',
          soft_formatted: '96.0GB',
          hard_formatted: '101.0GB',
          pressure_level: 'ok',
        },
        total_active_requests: 2,
        total_waiting_requests: 0,
      },
    },
  })
  upstreams.push(anthropic.server)

  await withBridge(
    t,
    [provider('omlx', 'anthropic', anthropic.baseUrl)],
    async bridge => {
      const response = await fetch(`${bridge.baseUrl}/v1/messages`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          model: 'omlx/Qwen3.6-27B-Heretic-MLX-bf16',
          max_tokens: 16,
          stream: true,
          messages: [{ role: 'user', content: 'think slowly' }],
        }),
      })

      assert.equal(response.ok, true)
      const text = await readChunksUntil(response, /prefill 8\.2k \/ 32\.8k tokens/)
      assert.match(text, /_Local model: prefill 8\.2k \/ 32\.8k tokens \(25%\), about 6m 22s left/)
      assert.match(text, /25%/)
      assert.doesNotMatch(text, /\*\*Local model status\*\*/)
      assert.doesNotMatch(text, /Memory:/)
    },
    {
      bridgeConfig: providersFile => ({
        ...bridgeConfig(providersFile, 'omlx/Qwen3.6-27B-Heretic-MLX-bf16'),
        streamingProgress: {
          enabled: true,
          delayMs: 25,
          intervalMs: 50,
        },
        thinking: {
          mode: 'suppress',
        },
      }),
    },
  )
})

test('emits compact heartbeat when provider progress bucket is unchanged', async t => {
  const upstreams = []
  t.after(async () => {
    await closeServers(upstreams)
  })

  const anthropic = await startThinkingOnlyAnthropicStreamingProvider({
    models: [model('Qwen3.6-27B-Heretic-MLX-bf16')],
    endDelayMs: 250,
    activity: {
      active_models: {
        models: [
          {
            id: 'Qwen3.6-27B-Heretic-MLX-bf16',
            is_loading: false,
            active_requests: 1,
            waiting_requests: 0,
            waiting: [],
            prefilling: [],
            generating: [],
            actual_size_formatted: '51.26GB',
          },
        ],
        total_active_requests: 1,
        total_waiting_requests: 0,
      },
    },
  })
  upstreams.push(anthropic.server)

  await withBridge(
    t,
    [provider('omlx', 'anthropic', anthropic.baseUrl)],
    async bridge => {
      const response = await fetch(`${bridge.baseUrl}/v1/messages`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          model: 'omlx/Qwen3.6-27B-Heretic-MLX-bf16',
          max_tokens: 16,
          stream: true,
          messages: [{ role: 'user', content: 'stay alive while status is unchanged' }],
        }),
      })

      assert.equal(response.ok, true)
      const text = await readChunksUntilCount(response, /_Local model:/g, 2)
      assert.match(text, /model loaded, waiting for output/)
    },
    {
      bridgeConfig: providersFile => ({
        ...bridgeConfig(providersFile, 'omlx/Qwen3.6-27B-Heretic-MLX-bf16'),
        streamingProgress: {
          enabled: true,
          delayMs: 10,
          intervalMs: 20,
          idleHeartbeatMs: 50,
        },
        thinking: {
          mode: 'suppress',
        },
      }),
    },
  )
})

test('rewrites Claude aliases for Anthropic messages subpaths', async t => {
  const upstreams = []
  t.after(async () => {
    await closeServers(upstreams)
  })

  const anthropic = await startAnthropicProvider({
    models: [model('Qwen3.6-27B-Heretic-MLX-bf16')],
  })
  upstreams.push(anthropic.server)

  await withBridge(
    t,
    [provider('omlx', 'anthropic', anthropic.baseUrl)],
    async bridge => {
      const response = await postJson(`${bridge.baseUrl}/v1/messages/count_tokens`, {
        model: 'claude-sonnet-4-6',
        messages: [{ role: 'user', content: 'hello' }],
      })

      assert.equal(response.input_tokens, 7)
      assert.equal(anthropic.requests.countTokens.length, 1)
      assert.equal(
        anthropic.requests.countTokens[0].model,
        'Qwen3.6-27B-Heretic-MLX-bf16',
      )
    },
    {
      bridgeConfig: providersFile => ({
        ...bridgeConfig(providersFile, 'claude-sonnet-4-6'),
        claudeDesktopModels: [
          {
            name: 'claude-sonnet-4-6',
            target: 'omlx/Qwen3.6-27B-Heretic-MLX-bf16',
          },
        ],
      }),
    },
  )
})

function bridgeConfig(providersFile, mainModel) {
  return {
    bridge: { host: '127.0.0.1' },
    providersFile,
    models: {
      main: mainModel,
      small: mainModel,
      tool: mainModel,
    },
    env: {
      OMLX_API_KEY: 'local-bridge',
    },
  }
}

function model(id, extra = {}) {
  return {
    id,
    object: 'model',
    created: 0,
    owned_by: 'test',
    ...extra,
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
  const bridgeConfigFile = path.join(workDir, 'bridge.local.json')
  const configFile = path.join(workDir, 'claude.json')
  const stdout = []
  const stderr = []

  await writeFile(providersFile, JSON.stringify({ providers }), 'utf8')
  if (options.bridgeConfig) {
    await writeFile(
      bridgeConfigFile,
      JSON.stringify(options.bridgeConfig(providersFile)),
      'utf8',
    )
  }

  const child = spawn(process.execPath, [BRIDGE_SCRIPT, 'serve'], {
    cwd: ROOT_DIR,
    env: {
      ...process.env,
      ...options.env,
      CLAUDE_LOCAL_BRIDGE_HOST: '127.0.0.1',
      CLAUDE_LOCAL_BRIDGE_PORT: String(port),
      ...(options.bridgeConfig
        ? { CLAUDE_LOCAL_CONFIG_FILE: bridgeConfigFile }
        : { CLAUDE_LOCAL_PROVIDERS_FILE: providersFile }),
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
      bridgeConfigFile,
      providersFile,
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
  const requests = { messages: [], countTokens: [] }
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

    if (req.method === 'POST' && req.url === '/v1/messages/count_tokens') {
      const body = await readJsonBody(req)
      requests.countTokens.push(body)
      return writeJson(res, 200, { input_tokens: 7 })
    }

    writeJson(res, 404, { error: `unexpected ${req.method} ${req.url}` })
  })

  const baseUrl = await listen(server)
  return { server, baseUrl, requests }
}

async function startSlowAnthropicStreamingProvider({ models, headerDelayMs }) {
  const requests = { messages: [] }
  const server = http.createServer(async (req, res) => {
    if (req.method === 'GET' && ['/api/v1/models', '/v1/models'].includes(req.url)) {
      return writeJson(res, 200, { object: 'list', data: models })
    }

    if (req.method === 'POST' && req.url === '/v1/messages') {
      const body = await readJsonBody(req)
      requests.messages.push(body)
      await new Promise(resolve => setTimeout(resolve, headerDelayMs))
      res.writeHead(200, {
        'content-type': 'text/event-stream; charset=utf-8',
        'cache-control': 'no-cache',
      })
      res.end(
        `event: message_stop\ndata: ${JSON.stringify({ type: 'message_stop' })}\n\n`,
      )
      return
    }

    writeJson(res, 404, { error: `unexpected ${req.method} ${req.url}` })
  })

  const baseUrl = await listen(server)
  return { server, baseUrl, requests }
}

async function startThinkingOnlyAnthropicStreamingProvider({
  models,
  activity = null,
  endDelayMs = 250,
}) {
  const requests = { messages: [] }
  const server = http.createServer(async (req, res) => {
    if (req.method === 'GET' && ['/api/v1/models', '/v1/models'].includes(req.url)) {
      return writeJson(res, 200, { object: 'list', data: models })
    }

    if (req.method === 'GET' && req.url === '/admin/api/activity' && activity) {
      return writeJson(res, 200, activity)
    }

    if (req.method === 'POST' && req.url === '/v1/messages') {
      const body = await readJsonBody(req)
      requests.messages.push(body)
      res.writeHead(200, {
        'content-type': 'text/event-stream; charset=utf-8',
        'cache-control': 'no-cache',
      })
      res.write(
        `event: message_start\ndata: ${JSON.stringify({
          type: 'message_start',
          message: {
            id: 'msg_thinking_only',
            type: 'message',
            role: 'assistant',
            model: body.model,
            content: [],
            stop_reason: null,
            stop_sequence: null,
            usage: { input_tokens: 1, output_tokens: 0 },
          },
        })}\n\n`,
      )
      res.write(
        `event: content_block_start\ndata: ${JSON.stringify({
          type: 'content_block_start',
          index: 0,
          content_block: { type: 'thinking', thinking: '', signature: 'test' },
        })}\n\n`,
      )
      res.write(
        `event: content_block_delta\ndata: ${JSON.stringify({
          type: 'content_block_delta',
          index: 0,
          delta: { type: 'thinking_delta', thinking: 'still thinking' },
        })}\n\n`,
      )
      setTimeout(() => {
        res.end(
          `event: message_stop\ndata: ${JSON.stringify({ type: 'message_stop' })}\n\n`,
        )
      }, endDelayMs)
      return
    }

    writeJson(res, 404, { error: `unexpected ${req.method} ${req.url}` })
  })

  const baseUrl = await listen(server)
  return { server, baseUrl, requests }
}

async function startThinkingThenTextAnthropicStreamingProvider({ models }) {
  const requests = { messages: [] }
  const server = http.createServer(async (req, res) => {
    if (req.method === 'GET' && ['/api/v1/models', '/v1/models'].includes(req.url)) {
      return writeJson(res, 200, { object: 'list', data: models })
    }

    if (req.method === 'POST' && req.url === '/v1/messages') {
      const body = await readJsonBody(req)
      requests.messages.push(body)
      res.writeHead(200, {
        'content-type': 'text/event-stream; charset=utf-8',
        'cache-control': 'no-cache',
      })
      res.write(
        `event: message_start\ndata: ${JSON.stringify({
          type: 'message_start',
          message: {
            id: 'msg_thinking_text',
            type: 'message',
            role: 'assistant',
            model: body.model,
            content: [],
            stop_reason: null,
            stop_sequence: null,
            usage: { input_tokens: 1, output_tokens: 0 },
          },
        })}\n\n`,
      )
      res.write(
        `event: content_block_start\ndata: ${JSON.stringify({
          type: 'content_block_start',
          index: 0,
          content_block: { type: 'thinking', thinking: '', signature: 'test' },
        })}\n\n`,
      )
      res.write(
        `event: content_block_delta\ndata: ${JSON.stringify({
          type: 'content_block_delta',
          index: 0,
          delta: { type: 'thinking_delta', thinking: 'still thinking' },
        })}\n\n`,
      )
      setTimeout(() => {
        res.write(
          `event: content_block_stop\ndata: ${JSON.stringify({
            type: 'content_block_stop',
            index: 0,
          })}\n\n`,
        )
        res.write(
          `event: content_block_start\ndata: ${JSON.stringify({
            type: 'content_block_start',
            index: 1,
            content_block: { type: 'text', text: '' },
          })}\n\n`,
        )
        res.write(
          `event: content_block_delta\ndata: ${JSON.stringify({
            type: 'content_block_delta',
            index: 1,
            delta: { type: 'text_delta', text: 'final answer' },
          })}\n\n`,
        )
        res.write(
          `event: content_block_stop\ndata: ${JSON.stringify({
            type: 'content_block_stop',
            index: 1,
          })}\n\n`,
        )
        res.end(
          `event: message_stop\ndata: ${JSON.stringify({ type: 'message_stop' })}\n\n`,
        )
      }, 80)
      return
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

async function readFirstChunk(response) {
  const reader = response.body.getReader()
  const { done, value } = await reader.read()
  assert.equal(done, false)
  await reader.cancel()
  return Buffer.from(value).toString('utf8')
}

async function readChunksUntil(response, pattern) {
  const reader = response.body.getReader()
  let text = ''
  const deadline = Date.now() + 3000
  try {
    while (Date.now() < deadline) {
      const { done, value } = await reader.read()
      if (done) {
        break
      }
      text += Buffer.from(value).toString('utf8')
      if (pattern.test(text)) {
        return text
      }
    }
  } finally {
    await reader.cancel()
  }
  assert.fail(`did not see ${pattern} in stream:\n${text}`)
}

async function readChunksUntilCount(response, pattern, count) {
  const reader = response.body.getReader()
  let text = ''
  const deadline = Date.now() + 3000
  try {
    while (Date.now() < deadline) {
      const { done, value } = await reader.read()
      if (done) {
        break
      }
      text += Buffer.from(value).toString('utf8')
      if ([...text.matchAll(pattern)].length >= count) {
        return text
      }
    }
  } finally {
    await reader.cancel()
  }
  assert.fail(`did not see ${count} matches for ${pattern} in stream:\n${text}`)
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
