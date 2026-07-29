#!/usr/bin/env node

import http from 'node:http'
import { existsSync } from 'node:fs'
import { mkdir, readFile, rename, writeFile } from 'node:fs/promises'
import { homedir } from 'node:os'
import path from 'node:path'
import { Readable } from 'node:stream'
import { pipeline } from 'node:stream/promises'

const BRIDGE_HOST = normalizeBridgeHost(process.env.CLAUDE_LOCAL_BRIDGE_HOST)
const BRIDGE_PORT = Number(
  process.env.CLAUDE_LOCAL_BRIDGE_PORT ?? '1245',
)
const MODEL_SYNC_INTERVAL_MS = Number(
  process.env.CLAUDE_LOCAL_MODEL_SYNC_INTERVAL_MS ?? '30000',
)
const REQUEST_TIMEOUT_MS = Number(
  process.env.CLAUDE_LOCAL_REQUEST_TIMEOUT_MS ?? '600000',
)
const TOOL_MODEL_OVERRIDE = process.env.CLAUDE_LOCAL_TOOL_MODEL ?? ''

const ANTHROPIC_FAMILY_PATTERNS = [
  'claude-',
  'sonnet',
  'opus',
  'haiku',
  'capybara',
]

let providers = []
let lastProviderConfigSignature = ''
let lastSyncedOptions = []
let modelRoutes = new Map()
let providerStatuses = []
let modelSelection = {
  mainModel: null,
  smallModel: null,
}

main().catch(error => {
  console.error(`[bridge] fatal: ${formatError(error)}`)
  process.exitCode = 1
})

async function main() {
  await reloadProviders({ force: true })
  const command = process.argv[2] ?? 'serve'

  switch (command) {
    case 'help':
    case '--help':
    case '-h':
      printHelp()
      return
    case 'sync-models': {
      const result = await syncModelOptions()
      console.log(
        `[bridge] synced ${result.options.length} model option(s) to ${result.configPath}`,
      )
      if (result.mainModel) {
        console.log(`[bridge] main model:  ${result.mainModel}`)
      }
      if (result.smallModel) {
        console.log(`[bridge] small model: ${result.smallModel}`)
      }
      return
    }
    case 'print-env': {
      const bridgeBaseUrl = `http://${BRIDGE_HOST}:${BRIDGE_PORT}`
      printEnvBlock(bridgeBaseUrl)
      return
    }
    case 'serve':
      // Keep the local endpoint available while a backend is restarting.
      // Periodic syncs and request handling will recover once it is reachable.
      try {
        await syncModelOptions()
      } catch (error) {
        console.error(
          `[bridge] initial model sync failed; starting anyway: ${formatError(error)}`,
        )
      }
      await startServer()
      return
    default:
      throw new Error(
        `unknown command "${command}". Use "serve", "sync-models", or "print-env".`,
      )
  }
}

function printHelp() {
  console.log(`Claude <-> local inference bridge

Usage:
  node bridge.mjs serve
  node bridge.mjs sync-models
  node bridge.mjs print-env

Environment:
  CLAUDE_LOCAL_PROVIDERS                  JSON array of provider definitions
  CLAUDE_LOCAL_PROVIDERS_FILE             JSON file to auto-reload provider definitions
  CLAUDE_LOCAL_INFERENCE_BACKEND          Single-provider fallback: lmstudio, omlx, openai, anthropic
  CLAUDE_LOCAL_INFERENCE_BASE_URL         Single-provider upstream base URL override
  CLAUDE_LOCAL_INFERENCE_API_KEY          Single-provider upstream API key override
  CLAUDE_LOCAL_INFERENCE_AUTH_SCHEME      Upstream auth: auto, none, bearer, x-api-key, both
  CLAUDE_LOCAL_INFERENCE_MODELS_FILE      Local JSON fixture for testing single-provider sync
  LMSTUDIO_BASE_URL                       LM Studio base URL (default: http://127.0.0.1:1234)
  LMSTUDIO_API_KEY                        Optional LM Studio API key to inject upstream
  OMLX_BASE_URL                           oMLX base URL (default: http://127.0.0.1:8000)
  OMLX_API_KEY                            Optional oMLX API key to inject upstream
  CLAUDE_LOCAL_BRIDGE_HOST                Loopback listen host only: 127.0.0.1, localhost, or ::1
  CLAUDE_LOCAL_BRIDGE_PORT                Bridge listen port (default: 1245)
  CLAUDE_LOCAL_MODEL_SYNC_INTERVAL_MS     Model sync interval in ms (default: 30000)
  CLAUDE_LOCAL_MAIN_MODEL                 Override default mapped main model
  CLAUDE_LOCAL_SMALL_MODEL                Override default mapped small/haiku model
  CLAUDE_LOCAL_TOOL_MODEL                 Override model used for tool-enabled /v1/messages requests
  CLAUDE_LOCAL_MODEL_MAP                  JSON object of explicit model rewrites
  CLAUDE_PROFILE_NAME                     Named Claude profile under ~/.claude-instances
  CLAUDE_PROFILE_DIR                      Explicit Claude profile user-data dir
  CLAUDE_GLOBAL_CONFIG_FILE               Override Claude global config path
  CLAUDE_CONFIG_DIR                       Alternate Claude config root
  LMSTUDIO_MODELS_FILE                    LM Studio-specific fixture alias`)
}

function printEnvBlock(bridgeBaseUrl) {
  const token =
    process.env.ANTHROPIC_API_KEY ||
    process.env.ANTHROPIC_AUTH_TOKEN ||
    'local-bridge'
  console.log(`export ANTHROPIC_BASE_URL=${bridgeBaseUrl}`)
  console.log(`export ANTHROPIC_API_KEY=${token}`)
  console.log(`export ANTHROPIC_AUTH_TOKEN=${token}`)
  console.log('export CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=1')
  console.log('export ENABLE_TOOL_SEARCH=false')
  console.log('export CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1')
  console.log('export CLAUDE_CODE_DISABLE_THINKING=1')
}

async function startServer() {
  const server = http.createServer(async (req, res) => {
    try {
      await routeRequest(req, res)
    } catch (error) {
      if (!res.headersSent) {
        res.writeHead(500, { 'content-type': 'application/json' })
      }
      res.end(
        JSON.stringify({
          error: formatError(error),
        }),
      )
    }
  })

  server.on('clientError', (_error, socket) => {
    socket.end('HTTP/1.1 400 Bad Request\r\n\r\n')
  })

  await new Promise((resolve, reject) => {
    server.once('error', reject)
    server.listen(BRIDGE_PORT, BRIDGE_HOST, resolve)
  })

  console.log(
    `[bridge] listening on http://${BRIDGE_HOST}:${BRIDGE_PORT} -> ${providers.length} provider(s)`,
  )
  printEnvBlock(`http://${BRIDGE_HOST}:${BRIDGE_PORT}`)

  const interval = setInterval(() => {
    syncModelOptions().catch(error => {
      console.error(`[bridge] model sync failed: ${formatError(error)}`)
    })
  }, MODEL_SYNC_INTERVAL_MS)
  interval.unref()
}

async function routeRequest(req, res) {
  const url = new URL(req.url ?? '/', `http://${req.headers.host ?? 'localhost'}`)

  if (url.pathname === '/healthz') {
    await syncModelOptions()
    return writeJson(res, 200, {
      ok: true,
      providers: providerStatuses,
      providerCount: providers.length,
      providerConfigSource: providerConfigSource(),
      providerConfigReloadable: Boolean(process.env.CLAUDE_LOCAL_PROVIDERS_FILE),
      models: lastSyncedOptions.length,
      mainModel: modelSelection.mainModel,
      smallModel: modelSelection.smallModel,
    })
  }

  if (url.pathname === '/sync-models') {
    const result = await syncModelOptions()
    return writeJson(res, 200, {
      ok: true,
      configPath: result.configPath,
      count: result.options.length,
      mainModel: result.mainModel,
      smallModel: result.smallModel,
      options: result.options,
    })
  }

  if (
    req.method === 'GET' &&
    url.pathname === '/api/claude_cli/bootstrap'
  ) {
    const result = await syncModelOptions()
    return writeJson(res, 200, {
      client_data: null,
      additional_model_options: result.options.map(option => ({
        model: option.value,
        name: option.label,
        description: option.description,
      })),
    })
  }

  if (
    req.method === 'GET' &&
    (url.pathname === '/v1/models' || url.pathname === '/api/v1/models')
  ) {
    const routeList = await buildGatewayModelList()
    if (routeList) {
      return writeJson(res, 200, routeList)
    }
  }

  if (url.pathname.startsWith('/v1/')) {
    return proxyToUpstream(req, res, url)
  }

  return writeJson(res, 404, {
    error: `unsupported path ${url.pathname}`,
  })
}

async function proxyToUpstream(req, res, url) {
  let provider = providers[0]
  let upstreamPath = url.pathname
  const headers = copyIncomingHeaders(req.headers)
  let expectsStreamingResponse = false

  let body
  if (req.method && !['GET', 'HEAD'].includes(req.method.toUpperCase())) {
    const rawBody = await readRequestBody(req)
    const prepared = await prepareRequestForProvider(url.pathname, rawBody)
    body = prepared.body
    provider = prepared.provider ?? provider
    upstreamPath = prepared.upstreamPath ?? upstreamPath
    expectsStreamingResponse = prepared.expectsStreamingResponse
  }

  const upstreamUrl = new URL(upstreamPath + url.search, provider.baseUrl)
  applyUpstreamAuthHeaders(headers, provider)

  let upstream
  try {
    upstream = await fetch(upstreamUrl, {
      method: req.method,
      headers,
      body,
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    })
  } catch (error) {
    console.error(
      `[bridge] upstream request failed for ${provider.id} ${req.method ?? 'GET'} ${upstreamUrl.pathname}: ${formatError(error)}`,
    )
    if (expectsStreamingResponse) {
      writeAnthropicSseError(
        res,
        502,
        `${provider.label} upstream request failed: ${formatError(error)}`,
      )
      return
    }
    throw error
  }

  if (
    provider.type === 'openai' &&
    url.pathname === '/v1/messages'
  ) {
    if (expectsStreamingResponse) {
      return writeOpenAiChatAsAnthropicSse(upstream, res, provider)
    }
    return writeOpenAiChatAsAnthropic(upstream, res, provider)
  }

  res.statusCode = upstream.status
  res.statusMessage = upstream.statusText
  upstream.headers.forEach((value, key) => {
    if (['content-length', 'connection', 'transfer-encoding'].includes(key)) {
      return
    }
    res.setHeader(key, value)
  })

  if (!upstream.body) {
    res.end()
    return
  }

  const isSseResponse = isEventStreamContentType(
    upstream.headers.get('content-type'),
  )

  try {
    await pipeline(Readable.fromWeb(upstream.body), res)
  } catch (error) {
    console.error(
      `[bridge] upstream stream failed for ${provider.id} ${req.method ?? 'GET'} ${upstreamUrl.pathname}: ${formatError(error)}`,
    )
    if (isSseResponse) {
      writeAnthropicSseError(
        res,
        upstream.status || 502,
        `${provider.label} stream closed unexpectedly: ${formatError(error)}`,
      )
      return
    }
    throw error
  }
}

async function prepareRequestForProvider(pathname, rawBody) {
  if (pathname !== '/v1/messages' || rawBody.length === 0) {
    return {
      body: rawBody,
      expectsStreamingResponse: false,
    }
  }

  let payload
  try {
    payload = JSON.parse(rawBody.toString('utf8'))
  } catch {
    return {
      body: rawBody,
      expectsStreamingResponse: false,
    }
  }

  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    return {
      body: rawBody,
      expectsStreamingResponse: false,
    }
  }

  const expectsStreamingResponse = payload.stream === true
  await syncModelOptions()

  if (typeof payload.model !== 'string' || payload.model.length === 0) {
    return {
      body: rawBody,
      expectsStreamingResponse,
    }
  }

  const route = resolveModelRoute(payload.model, payload)
  if (!route) {
    throw new Error(`unknown model route "${payload.model}"`)
  }

  if (payload.model !== route.upstreamModelId) {
    console.log(
      `[bridge] route model "${payload.model}" -> ${route.provider.id}/${route.upstreamModelId}`,
    )
  }

  payload.model = route.upstreamModelId
  if (route.provider.type === 'openai') {
    return {
      provider: route.provider,
      upstreamPath: '/v1/chat/completions',
      body: Buffer.from(JSON.stringify(toOpenAiChatCompletion(payload)), 'utf8'),
      expectsStreamingResponse,
    }
  }

  return {
    provider: route.provider,
    upstreamPath: '/v1/messages',
    body: Buffer.from(JSON.stringify(payload), 'utf8'),
    expectsStreamingResponse,
  }
}

function resolveModelRoute(requestedModel, payload = null) {
  const normalized = requestedModel.toLowerCase()
  const exact = modelRoutes.get(requestedModel)
  if (exact) {
    return exact
  }

  const exactCaseInsensitive = [...modelRoutes.entries()].find(
    ([routeId]) => routeId.toLowerCase() === normalized,
  )
  if (exactCaseInsensitive) {
    return exactCaseInsensitive[1]
  }

  const preferredToolModel = pickToolAwareModel(payload, normalized)
  if (preferredToolModel) {
    return preferredToolModel
  }

  const explicitMap = parseExplicitModelMap()
  if (explicitMap.has(requestedModel)) {
    return routeForTargetModel(explicitMap.get(requestedModel))
  }

  const caseInsensitiveMatch = [...explicitMap.entries()].find(
    ([key]) => key.toLowerCase() === normalized,
  )
  if (caseInsensitiveMatch) {
    return routeForTargetModel(caseInsensitiveMatch[1])
  }

  if (normalized.includes('haiku')) {
    return routeForTargetModel(modelSelection.smallModel ?? modelSelection.mainModel)
  }

  if (
    normalized === 'default' ||
    normalized === 'best' ||
    ANTHROPIC_FAMILY_PATTERNS.some(pattern => normalized.includes(pattern))
  ) {
    return routeForTargetModel(modelSelection.mainModel)
  }

  return null
}

function pickToolAwareModel(payload, normalizedRequestedModel) {
  if (!payloadHasTools(payload)) {
    return null
  }

  if (!looksLikeAnthropicAlias(normalizedRequestedModel)) {
    return null
  }

  return (
    pickConfiguredModelId(TOOL_MODEL_OVERRIDE) ??
    routeForTargetModel(modelSelection.smallModel) ??
    null
  )
}

function payloadHasTools(payload) {
  return Boolean(
    payload &&
      typeof payload === 'object' &&
      Array.isArray(payload.tools) &&
      payload.tools.length > 0,
  )
}

function looksLikeAnthropicAlias(normalizedRequestedModel) {
  return (
    normalizedRequestedModel === 'default' ||
    normalizedRequestedModel === 'best' ||
    ANTHROPIC_FAMILY_PATTERNS.some(pattern =>
      normalizedRequestedModel.includes(pattern),
    )
  )
}

function pickConfiguredModelId(candidate) {
  if (!candidate) {
    return null
  }

  const exact = modelRoutes.get(candidate)
  if (exact) {
    return exact
  }

  const normalized = candidate.toLowerCase()
  const caseInsensitive = [...modelRoutes.entries()].find(
    ([routeId]) => routeId.toLowerCase() === normalized,
  )
  if (caseInsensitive) {
    return caseInsensitive[1]
  }

  return null
}

function routeForTargetModel(candidate) {
  if (!candidate) {
    return null
  }
  const exact = modelRoutes.get(candidate)
  if (exact) {
    return exact
  }

  const caseInsensitive = [...modelRoutes.entries()].find(
    ([routeId]) => routeId.toLowerCase() === candidate.toLowerCase(),
  )
  if (caseInsensitive) {
    return caseInsensitive[1]
  }

  const upstreamMatch = [...modelRoutes.values()].find(
    route => route.upstreamModelId === candidate,
  )
  if (upstreamMatch) {
    return upstreamMatch
  }

  const upstreamCaseInsensitive = [...modelRoutes.values()].find(
    route => route.upstreamModelId.toLowerCase() === candidate.toLowerCase(),
  )
  return upstreamCaseInsensitive ?? null
}

function toOpenAiChatCompletion(payload) {
  const messages = []
  const systemText = anthropicTextFromContent(payload.system)
  if (systemText) {
    messages.push({ role: 'system', content: systemText })
  }

  for (const message of Array.isArray(payload.messages) ? payload.messages : []) {
    const role = message?.role === 'assistant' ? 'assistant' : 'user'
    messages.push({
      role,
      content: anthropicTextFromContent(message?.content),
    })
  }

  const next = {
    model: payload.model,
    messages,
    stream: false,
  }

  if (typeof payload.max_tokens === 'number') {
    next.max_tokens = payload.max_tokens
  }
  if (typeof payload.temperature === 'number') {
    next.temperature = payload.temperature
  }
  if (typeof payload.top_p === 'number') {
    next.top_p = payload.top_p
  }
  if (Array.isArray(payload.stop_sequences)) {
    next.stop = payload.stop_sequences
  }
  if (Array.isArray(payload.tools) && payload.tools.length > 0) {
    next.tools = payload.tools.map(toOpenAiTool).filter(Boolean)
  }
  if (payload.tool_choice) {
    next.tool_choice = toOpenAiToolChoice(payload.tool_choice)
  }

  return next
}

function anthropicTextFromContent(content) {
  if (typeof content === 'string') {
    return content
  }
  if (!Array.isArray(content)) {
    return ''
  }

  return content
    .map(part => {
      if (typeof part === 'string') {
        return part
      }
      if (part?.type === 'text' && typeof part.text === 'string') {
        return part.text
      }
      if (part?.type === 'tool_result') {
        return anthropicTextFromContent(part.content)
      }
      return ''
    })
    .filter(Boolean)
    .join('\n')
}

function toOpenAiTool(tool) {
  if (!tool || typeof tool !== 'object' || typeof tool.name !== 'string') {
    return null
  }
  return {
    type: 'function',
    function: {
      name: tool.name,
      description: typeof tool.description === 'string' ? tool.description : '',
      parameters: tool.input_schema ?? { type: 'object', properties: {} },
    },
  }
}

function toOpenAiToolChoice(choice) {
  if (choice === 'auto' || choice?.type === 'auto') {
    return 'auto'
  }
  if (choice === 'any' || choice?.type === 'any') {
    return 'required'
  }
  if (choice?.type === 'tool' && typeof choice.name === 'string') {
    return {
      type: 'function',
      function: { name: choice.name },
    }
  }
  return choice
}

async function writeOpenAiChatAsAnthropic(upstream, res, provider) {
  const text = await upstream.text()
  let payload
  try {
    payload = JSON.parse(text)
  } catch {
    res.writeHead(upstream.status, {
      'content-type': upstream.headers.get('content-type') ?? 'text/plain',
    })
    res.end(text)
    return
  }

  if (!upstream.ok) {
    return writeJson(res, upstream.status, payload)
  }

  return writeJson(res, 200, openAiChatToAnthropicMessage(payload, provider))
}

async function writeOpenAiChatAsAnthropicSse(upstream, res, provider) {
  const text = await upstream.text()
  let payload
  try {
    payload = JSON.parse(text)
  } catch {
    writeAnthropicSseError(res, upstream.status, `${provider.label} returned non-JSON OpenAI response`)
    return
  }

  if (!upstream.ok) {
    writeAnthropicSseError(
      res,
      upstream.status,
      payload?.error?.message ?? `${provider.label} OpenAI request failed`,
    )
    return
  }

  const message = openAiChatToAnthropicMessage(payload, provider)
  if (!res.headersSent) {
    res.statusCode = 200
    res.setHeader('content-type', 'text/event-stream; charset=utf-8')
    res.setHeader('cache-control', 'no-cache')
  }

  res.write(`event: message_start\ndata: ${JSON.stringify({ type: 'message_start', message })}\n\n`)
  for (const [index, block] of message.content.entries()) {
    res.write(
      `event: content_block_start\ndata: ${JSON.stringify({
        type: 'content_block_start',
        index,
        content_block: block.type === 'text' ? { type: 'text', text: '' } : block,
      })}\n\n`,
    )
    if (block.type === 'text') {
      res.write(
        `event: content_block_delta\ndata: ${JSON.stringify({
          type: 'content_block_delta',
          index,
          delta: { type: 'text_delta', text: block.text },
        })}\n\n`,
      )
    }
    res.write(`event: content_block_stop\ndata: ${JSON.stringify({ type: 'content_block_stop', index })}\n\n`)
  }
  res.write(
    `event: message_delta\ndata: ${JSON.stringify({
      type: 'message_delta',
      delta: { stop_reason: message.stop_reason, stop_sequence: null },
      usage: { output_tokens: message.usage.output_tokens },
    })}\n\n`,
  )
  res.write(`event: message_stop\ndata: ${JSON.stringify({ type: 'message_stop' })}\n\n`)
  res.end()
}

function openAiChatToAnthropicMessage(payload, provider) {
  const choice = payload.choices?.[0] ?? {}
  const message = choice.message ?? {}
  const content = []
  if (typeof message.content === 'string' && message.content.length > 0) {
    content.push({ type: 'text', text: message.content })
  }
  if (Array.isArray(message.tool_calls)) {
    for (const toolCall of message.tool_calls) {
      const fn = toolCall.function ?? {}
      content.push({
        type: 'tool_use',
        id: toolCall.id ?? `toolu_${Math.random().toString(36).slice(2)}`,
        name: fn.name ?? 'tool',
        input: parseJsonObject(fn.arguments),
      })
    }
  }

  return {
    id: payload.id ?? `msg_${Date.now()}`,
    type: 'message',
    role: 'assistant',
    model: message.model ?? payload.model ?? provider.id,
    content,
    stop_reason: openAiFinishReasonToAnthropic(choice.finish_reason),
    stop_sequence: null,
    usage: {
      input_tokens: payload.usage?.prompt_tokens ?? 0,
      output_tokens: payload.usage?.completion_tokens ?? 0,
    },
  }
}

function openAiFinishReasonToAnthropic(reason) {
  if (reason === 'tool_calls') {
    return 'tool_use'
  }
  if (reason === 'length') {
    return 'max_tokens'
  }
  if (reason === 'stop') {
    return 'end_turn'
  }
  return reason ?? 'end_turn'
}

function parseJsonObject(value) {
  if (typeof value !== 'string' || !value.trim()) {
    return {}
  }
  try {
    const parsed = JSON.parse(value)
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed)
      ? parsed
      : {}
  } catch {
    return {}
  }
}

function parseExplicitModelMap() {
  const raw = process.env.CLAUDE_LOCAL_MODEL_MAP
  if (!raw) {
    return new Map()
  }

  try {
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      return new Map()
    }

    return new Map(
      Object.entries(parsed).filter(
        ([key, value]) =>
          typeof key === 'string' &&
          key.length > 0 &&
          typeof value === 'string' &&
          value.length > 0,
      ),
    )
  } catch {
    console.error('[bridge] ignoring invalid CLAUDE_LOCAL_MODEL_MAP JSON')
    return new Map()
  }
}

async function buildGatewayModelList() {
  await syncModelOptions()
  return {
    object: 'list',
    data: lastSyncedOptions.map(option => ({
      id: option.value,
      object: 'model',
      created: 0,
      owned_by: option.providerId ?? 'local',
    })),
  }
}

async function syncModelOptions() {
  await reloadProviders()
  const results = await Promise.all(
    providers.filter(provider => provider.enabled).map(async provider => {
      try {
        return {
          ok: true,
          provider,
          payload: await fetchProviderModelsPayload(provider),
        }
      } catch (error) {
        return {
          ok: false,
          provider,
          error,
        }
      }
    }),
  )

  const nextStatuses = []
  const optionsById = new Map()
  const routesById = new Map()

  for (const result of results) {
    if (!result.ok) {
      nextStatuses.push({
        ok: false,
        id: result.provider.id,
        type: result.provider.type,
        baseUrl: result.provider.baseUrl,
        error: formatError(result.error),
      })
      continue
    }

    const { provider, payload } = result
    const options = normalizeModelOptions(payload, provider)
    nextStatuses.push({
      ok: true,
      id: provider.id,
      type: provider.type,
      baseUrl: provider.baseUrl,
      models: options.length,
    })

    for (const option of options) {
      optionsById.set(option.value, option)
      routesById.set(option.value, {
        routeId: option.value,
        upstreamModelId: option.upstreamModelId,
        provider,
      })
    }
  }

  const options = [...optionsById.values()].sort((a, b) => {
    return a.label.localeCompare(b.label) || a.value.localeCompare(b.value)
  })
  if (options.length === 0) {
    providerStatuses = nextStatuses
    throw new Error('no configured provider returned any usable LLM models')
  }

  lastSyncedOptions = options
  modelRoutes = routesById
  providerStatuses = nextStatuses
  modelSelection = chooseDefaultModels(options)

  const configPath = await getClaudeGlobalConfigPath()
  const config = await readJsonObject(configPath)

  const nextConfig = {
    ...config,
    additionalModelOptionsCache: options,
  }

  if (
    JSON.stringify(config.additionalModelOptionsCache ?? []) !==
    JSON.stringify(options)
  ) {
    await writeJsonObject(configPath, nextConfig)
  }

  return {
    configPath,
    options,
    mainModel: modelSelection.mainModel,
    smallModel: modelSelection.smallModel,
  }
}

async function fetchModelsPayload() {
  return fetchProviderModelsPayload(providers[0])
}

async function fetchProviderModelsPayload(provider) {
  if (provider.modelsFile) {
    const fixture = await readFile(provider.modelsFile, 'utf8')
    return JSON.parse(fixture)
  }

  const candidates =
    provider.type === 'openai'
      ? ['/v1/models', '/api/v1/models']
      : ['/api/v1/models', '/v1/models']
  let lastError

  for (const candidate of candidates) {
    try {
      const response = await fetch(new URL(candidate, provider.baseUrl), {
        headers: buildUpstreamHeaders(provider),
        signal: AbortSignal.timeout(5000),
      })

      if (!response.ok) {
        throw new Error(`HTTP ${response.status} for ${candidate}`)
      }

      return await response.json()
    } catch (error) {
      lastError = error
    }
  }

  throw lastError ?? new Error(`failed to fetch models from ${provider.label}`)
}

function normalizeModelOptions(payload, provider = providers[0]) {
  const models = coerceModelsArray(payload)
  const optionsById = new Map()

  for (const model of models) {
    const option = normalizeModelOption(model, provider)
    if (!option) {
      continue
    }
    optionsById.set(option.value, option)
  }

  return [...optionsById.values()].sort((a, b) => {
    return a.label.localeCompare(b.label) || a.value.localeCompare(b.value)
  })
}

function normalizeModelOption(model, provider = providers[0]) {
  const type = String(model?.type ?? '').toLowerCase()
  if (type && type !== 'llm' && type !== 'model') {
    return null
  }

  const id = firstString(
    model?.id,
    model?.key,
    model?.model,
    model?.modelKey,
    model?.identifier,
    model?.name,
  )
  if (!id) {
    return null
  }
  if (isNonConversationModelId(id)) {
    return null
  }

  const baseLabel =
    firstString(model?.displayName, model?.display_name, model?.name) ??
    prettifyModelId(id)
  const label = provider.labelPrefix
    ? `${provider.labelPrefix}${baseLabel}`
    : `${provider.label}: ${baseLabel}`

  const descriptionParts = []
  const paramsString = firstString(model?.paramsString, model?.params_string)
  if (paramsString) {
    descriptionParts.push(paramsString)
  }
  if (typeof model?.architecture === 'string' && model.architecture.trim()) {
    descriptionParts.push(model.architecture.trim())
  }
  const quantizationName = firstString(
    model?.quantization?.name,
    model?.quantizationName,
  )
  if (quantizationName) {
    descriptionParts.push(quantizationName)
  }
  const maxContextLength = firstNumber(
    model?.maxContextLength,
    model?.max_context_length,
  )
  if (maxContextLength !== null) {
    descriptionParts.push(`${compactNumber(maxContextLength)} ctx`)
  }
  const isLoaded =
    model?.loaded === true ||
    (Array.isArray(model?.loaded_instances) && model.loaded_instances.length > 0)
  if (model?.loaded === true || Array.isArray(model?.loaded_instances)) {
    descriptionParts.push(isLoaded ? 'loaded' : 'not loaded')
  }
  if (
    model?.trainedForToolUse === true ||
    model?.capabilities?.trained_for_tool_use === true
  ) {
    descriptionParts.push('tool use')
  }
  if (
    model?.vision === true ||
    model?.capabilities?.vision === true
  ) {
    descriptionParts.push('vision')
  }

  const description =
    descriptionParts.length > 0
      ? descriptionParts.join(' · ')
      : `${provider.label} model (${id})`

  const routeId = buildModelRouteId(provider, id)
  return {
    value: routeId,
    providerId: provider.id,
    upstreamModelId: id,
    label,
    description,
  }
}

function chooseDefaultModels(options) {
  const byId = new Map(options.map(option => [option.value, option]))

  const envMain = process.env.CLAUDE_LOCAL_MAIN_MODEL
  const envSmall = process.env.CLAUDE_LOCAL_SMALL_MODEL

  const mainModel =
    (envMain && byId.has(envMain) && envMain) ||
    chooseBestModelId(options, { preferSmall: false }) ||
    options[0]?.value ||
    null

  const smallModel =
    (envSmall && byId.has(envSmall) && envSmall) ||
    chooseBestModelId(options, { preferSmall: true }) ||
    mainModel

  return {
    mainModel,
    smallModel,
  }
}

function chooseBestModelId(models, { preferSmall }) {
  const candidates = models
    .map(model => ({
      id: firstString(
        model?.value,
        model?.id,
        model?.key,
        model?.model,
        model?.modelKey,
        model?.identifier,
        model?.name,
      ),
      type: String(model?.type ?? '').toLowerCase(),
      loaded:
        model?.loaded === true ||
        (Array.isArray(model?.loaded_instances) &&
          model.loaded_instances.length > 0),
      toolUse:
        model?.trainedForToolUse === true ||
        model?.capabilities?.trained_for_tool_use === true,
      hint:
        firstString(model?.label, model?.displayName, model?.display_name, model?.name) ?? '',
      params:
        parseParamsString(
          firstString(model?.paramsString, model?.params_string),
        ) ??
        inferParamsFromText(
          firstString(
            model?.id,
            model?.key,
            model?.model,
            model?.modelKey,
            model?.identifier,
            model?.name,
            model?.displayName,
            model?.display_name,
            model?.label,
          ) ?? '',
        ),
    }))
    .filter(model => model.id)
    .filter(model => !isNonConversationModelId(model.id))
    .filter(model => !model.type || model.type === 'llm' || model.type === 'model')

  if (candidates.length === 0) {
    return null
  }

  const sorted = candidates.sort((a, b) => {
    const aScore = modelSortScore(a, preferSmall)
    const bScore = modelSortScore(b, preferSmall)
    return bScore - aScore || a.id.localeCompare(b.id)
  })

  return sorted[0]?.id ?? null
}

function modelSortScore(model, preferSmall) {
  let score = 0
  if (model.loaded) {
    score += 1000
  }
  if (model.toolUse) {
    score += 500
  }
  if (/coder/i.test(`${model.id} ${model.hint}`)) {
    score += preferSmall ? 550 : 150
  }
  if (/(instruct|chat)/i.test(`${model.id} ${model.hint}`)) {
    score += 100
  }
  if (isAbliteratedModel(model)) {
    score += preferSmall ? 300 : 600
  }

  if (typeof model.params === 'number') {
    if (preferSmall) {
      if (model.params <= 8_500_000_000) {
        score += 400
      }
      score -= model.params / 1_000_000_000_000
    } else {
      score += model.params / 1_000_000_000
    }
  } else if (preferSmall) {
    score -= 1
  }

  return score
}

function isAbliteratedModel(model) {
  return /(abliterat|uncensor)/i.test(`${model.id} ${model.hint}`)
}

function isNonConversationModelId(id) {
  return /(embedding|reranker|hidream|image|visualquality)/i.test(id)
}

function parseParamsString(paramsString) {
  if (typeof paramsString !== 'string') {
    return null
  }

  const match = paramsString.trim().match(/(\d+(?:\.\d+)?)\s*([bm])/i)
  if (!match) {
    return null
  }

  const value = Number(match[1])
  const unit = match[2].toLowerCase()
  if (!Number.isFinite(value)) {
    return null
  }

  return unit === 'b' ? value * 1_000_000_000 : value * 1_000_000
}

function inferParamsFromText(value) {
  if (typeof value !== 'string') {
    return null
  }

  const match = value.match(/(?:^|[^\d])(\d+(?:\.\d+)?)\s*([bm])(?:$|[^\w])/i)
  if (!match) {
    return null
  }

  const amount = Number(match[1])
  if (!Number.isFinite(amount)) {
    return null
  }

  return match[2].toLowerCase() === 'b'
    ? amount * 1_000_000_000
    : amount * 1_000_000
}

function coerceModelsArray(payload) {
  if (Array.isArray(payload)) {
    return payload
  }
  if (payload && typeof payload === 'object') {
    if (Array.isArray(payload.data)) {
      return payload.data
    }
    if (Array.isArray(payload.models)) {
      return payload.models
    }
    if (Array.isArray(payload.items)) {
      return payload.items
    }
  }
  return []
}

async function reloadProviders({ force = false } = {}) {
  const nextProviders = await loadProviders()
  const nextSignature = stableJson(
    nextProviders.map(provider => ({
      id: provider.id,
      type: provider.type,
      backend: provider.backend,
      baseUrl: provider.baseUrl,
      authScheme: provider.authScheme,
      modelsFile: provider.modelsFile,
      enabled: provider.enabled,
    })),
  )

  if (!force && nextSignature === lastProviderConfigSignature) {
    return false
  }

  providers = nextProviders
  lastProviderConfigSignature = nextSignature
  lastSyncedOptions = []
  modelRoutes = new Map()
  modelSelection = {
    mainModel: null,
    smallModel: null,
  }
  console.log(`[bridge] loaded ${providers.length} provider(s)`)
  return true
}

async function loadProviders() {
  const configured = await parseProvidersConfig()
  const providers = configured.length > 0 ? configured : [singleProviderFromEnv()]
  return providers.map(normalizeProvider).filter(provider => provider.enabled)
}

async function parseProvidersConfig() {
  const fromFile = await parseProvidersFromFile()
  if (fromFile.length > 0) {
    return fromFile
  }
  return parseProvidersFromEnv()
}

async function parseProvidersFromFile() {
  const filePath = process.env.CLAUDE_LOCAL_PROVIDERS_FILE
  if (!filePath) {
    return []
  }

  try {
    const content = await readFile(filePath, 'utf8')
    return parseProvidersJson(content, `CLAUDE_LOCAL_PROVIDERS_FILE ${filePath}`)
  } catch (error) {
    console.error(`[bridge] ignoring unreadable CLAUDE_LOCAL_PROVIDERS_FILE ${filePath}: ${formatError(error)}`)
    return []
  }
}

function parseProvidersFromEnv() {
  const raw = process.env.CLAUDE_LOCAL_PROVIDERS
  if (!raw) {
    return []
  }

  return parseProvidersJson(raw, 'CLAUDE_LOCAL_PROVIDERS')
}

function parseProvidersJson(raw, sourceName) {
  try {
    const parsed = JSON.parse(raw)
    if (Array.isArray(parsed)) {
      return parsed
    }
    if (parsed && typeof parsed === 'object' && Array.isArray(parsed.providers)) {
      return parsed.providers
    }
  } catch (error) {
    console.error(`[bridge] ignoring invalid ${sourceName} JSON: ${formatError(error)}`)
  }
  return []
}

function singleProviderFromEnv() {
  const backend = normalizeBackendKind(
    process.env.CLAUDE_LOCAL_INFERENCE_BACKEND ??
      (process.env.OMLX_BASE_URL ? 'omlx' : 'lmstudio'),
  )
  const baseUrl = stripTrailingSlash(
    process.env.CLAUDE_LOCAL_INFERENCE_BASE_URL ??
      (backend === 'omlx'
        ? process.env.OMLX_BASE_URL ?? 'http://127.0.0.1:8000'
        : backend === 'openai'
          ? process.env.OPENAI_BASE_URL ?? 'https://api.openai.com'
          : backend === 'anthropic' || backend === 'claude'
            ? process.env.ANTHROPIC_BASE_URL ?? 'https://api.anthropic.com'
            : process.env.LMSTUDIO_BASE_URL ?? 'http://127.0.0.1:1234'),
  )
  return {
    id: backend,
    type: backend === 'openai' ? 'openai' : 'anthropic',
    baseUrl,
    apiKey:
      process.env.CLAUDE_LOCAL_INFERENCE_API_KEY ??
      (backend === 'omlx'
        ? process.env.OMLX_API_KEY ?? ''
        : backend === 'openai'
          ? process.env.OPENAI_API_KEY ?? ''
          : backend === 'anthropic' || backend === 'claude'
            ? process.env.ANTHROPIC_API_KEY ?? ''
            : process.env.LMSTUDIO_API_KEY ?? ''),
    authScheme: process.env.CLAUDE_LOCAL_INFERENCE_AUTH_SCHEME ?? 'auto',
    modelsFile:
      process.env.CLAUDE_LOCAL_INFERENCE_MODELS_FILE ??
      process.env.LMSTUDIO_MODELS_FILE,
  }
}

function normalizeProvider(provider, index) {
  const id = sanitizeProviderId(
    firstString(provider?.id, provider?.name) ?? `provider${index + 1}`,
  )
  const backend = normalizeBackendKind(provider?.backend ?? provider?.kind ?? id)
  const type = normalizeProviderType(provider?.type ?? backend)
  const baseUrl = stripTrailingSlash(
    firstString(provider?.baseUrl, provider?.base_url, provider?.url) ??
      (backend === 'omlx'
        ? 'http://127.0.0.1:8000'
        : backend === 'openai'
          ? 'https://api.openai.com'
          : backend === 'anthropic' || backend === 'claude'
            ? 'https://api.anthropic.com'
            : 'http://127.0.0.1:1234'),
  )
  return {
    id,
    label: firstString(provider?.label, provider?.displayName) ?? id,
    labelPrefix: firstString(provider?.labelPrefix, provider?.label_prefix),
    type,
    backend,
    baseUrl,
    apiKey: firstString(provider?.apiKey, provider?.api_key) ?? envValue(provider?.apiKeyEnv ?? provider?.api_key_env) ?? '',
    authScheme: normalizeAuthScheme(provider?.authScheme ?? provider?.auth_scheme ?? 'auto'),
    anthropicVersion: firstString(provider?.anthropicVersion, provider?.anthropic_version),
    modelsFile: firstString(provider?.modelsFile, provider?.models_file),
    enabled: provider?.enabled !== false,
  }
}

function sanitizeProviderId(value) {
  return String(value)
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_.-]+/g, '-')
    .replace(/^-+|-+$/g, '') || 'provider'
}

function normalizeProviderType(value) {
  const normalized = String(value ?? '')
    .trim()
    .toLowerCase()
  if (['openai', 'chat-completions', 'chat_completions'].includes(normalized)) {
    return 'openai'
  }
  return 'anthropic'
}

function envValue(name) {
  if (typeof name !== 'string' || !name.trim()) {
    return ''
  }
  return process.env[name.trim()] ?? ''
}

function providerConfigSource() {
  if (process.env.CLAUDE_LOCAL_PROVIDERS_FILE) {
    return process.env.CLAUDE_LOCAL_PROVIDERS_FILE
  }
  if (process.env.CLAUDE_LOCAL_PROVIDERS) {
    return 'CLAUDE_LOCAL_PROVIDERS'
  }
  return 'single-provider-env'
}

function stableJson(value) {
  return JSON.stringify(value, (_key, nestedValue) => {
    if (!nestedValue || typeof nestedValue !== 'object' || Array.isArray(nestedValue)) {
      return nestedValue
    }
    return Object.fromEntries(
      Object.entries(nestedValue).sort(([left], [right]) =>
        left.localeCompare(right),
      ),
    )
  })
}

function normalizeBridgeHost(value) {
  const host = String(value ?? '127.0.0.1').trim() || '127.0.0.1'
  if (host === '127.0.0.1' || host === 'localhost' || host === '::1') {
    return host
  }

  console.warn(
    `[bridge] refusing non-loopback CLAUDE_LOCAL_BRIDGE_HOST="${host}"; binding to 127.0.0.1`,
  )
  return '127.0.0.1'
}

function buildModelRouteId(provider, upstreamModelId) {
  if (!process.env.CLAUDE_LOCAL_PROVIDERS && !process.env.CLAUDE_LOCAL_PROVIDERS_FILE && providers.length === 1) {
    return upstreamModelId
  }
  return `${provider.id}/${upstreamModelId}`
}

function copyIncomingHeaders(headers) {
  const copied = new Headers()

  for (const [key, value] of Object.entries(headers)) {
    if (
      value == null ||
      ['host', 'connection', 'content-length', 'authorization', 'x-api-key'].includes(
        key.toLowerCase(),
      )
    ) {
      continue
    }

    if (Array.isArray(value)) {
      for (const item of value) {
        copied.append(key, item)
      }
    } else {
      copied.set(key, value)
    }
  }

  return copied
}

function buildUpstreamHeaders(provider = providers[0]) {
  const headers = new Headers()
  applyUpstreamAuthHeaders(headers, provider)
  if (provider.type === 'anthropic' && (provider.backend === 'anthropic' || provider.backend === 'claude')) {
    headers.set('anthropic-version', provider.anthropicVersion ?? '2023-06-01')
  }
  return headers
}

function applyUpstreamAuthHeaders(headers, provider = providers[0]) {
  if (!provider?.apiKey || provider.authScheme === 'none') {
    return
  }

  const authScheme =
    provider.authScheme === 'auto'
      ? provider.type === 'openai'
        ? 'bearer'
        : provider.backend === 'lmstudio'
          ? 'x-api-key'
          : provider.backend === 'anthropic' || provider.backend === 'claude'
            ? 'x-api-key'
            : 'bearer'
      : provider.authScheme

  if (authScheme === 'x-api-key' || authScheme === 'both') {
    headers.set('x-api-key', provider.apiKey)
  }

  if (authScheme === 'bearer' || authScheme === 'both') {
    headers.set('authorization', `Bearer ${provider.apiKey}`)
  }
}

function isEventStreamContentType(contentType) {
  return String(contentType ?? '')
    .toLowerCase()
    .includes('text/event-stream')
}

function writeAnthropicSseError(res, statusCode, message) {
  if (!res.headersSent) {
    res.statusCode = statusCode
    res.setHeader('content-type', 'text/event-stream; charset=utf-8')
    res.setHeader('cache-control', 'no-cache')
  }

  if (res.writableEnded || res.destroyed) {
    return
  }

  res.write(
    `event: error\ndata: ${JSON.stringify({
      type: 'error',
      error: {
        type: 'api_error',
        message,
      },
    })}\n\n`,
  )
  res.end()
}

async function readRequestBody(req) {
  const chunks = []
  for await (const chunk of req) {
    chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk))
  }
  return Buffer.concat(chunks)
}

function writeJson(res, statusCode, payload) {
  const body = JSON.stringify(payload, null, 2)
  res.writeHead(statusCode, {
    'content-type': 'application/json',
    'content-length': Buffer.byteLength(body),
  })
  res.end(body)
}

async function readJsonObject(filePath) {
  try {
    const content = await readFile(filePath, 'utf8')
    const parsed = JSON.parse(content)
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      return {}
    }
    return parsed
  } catch (error) {
    if (error?.code === 'ENOENT') {
      return {}
    }
    throw error
  }
}

async function writeJsonObject(filePath, payload) {
  await mkdir(path.dirname(filePath), { recursive: true })
  const tempPath = `${filePath}.tmp-${process.pid}`
  const body = `${JSON.stringify(payload, null, 2)}\n`
  await writeFile(tempPath, body, 'utf8')
  await rename(tempPath, filePath)
}

async function getClaudeGlobalConfigPath() {
  if (process.env.CLAUDE_GLOBAL_CONFIG_FILE) {
    return process.env.CLAUDE_GLOBAL_CONFIG_FILE
  }

  const profileDir = getClaudeProfileDir()
  if (profileDir) {
    const profileLegacyPath = path.join(profileDir, '.config.json')
    if (existsSync(profileLegacyPath)) {
      return profileLegacyPath
    }
    return path.join(profileDir, '.claude.json')
  }

  const claudeConfigDir = (
    process.env.CLAUDE_CONFIG_DIR ?? path.join(homedir(), '.claude')
  ).normalize('NFC')
  const legacyPath = path.join(claudeConfigDir, '.config.json')
  if (existsSync(legacyPath)) {
    return legacyPath
  }

  return path.join(process.env.CLAUDE_CONFIG_DIR ?? homedir(), '.claude.json')
}

function getClaudeProfileDir() {
  if (process.env.CLAUDE_PROFILE_DIR) {
    return process.env.CLAUDE_PROFILE_DIR
  }

  const profileName = firstString(process.env.CLAUDE_PROFILE_NAME)
  if (!profileName || profileName === 'default') {
    return null
  }

  return path.join(homedir(), '.claude-instances', profileName)
}

function firstString(...values) {
  for (const value of values) {
    if (typeof value === 'string' && value.trim()) {
      return value.trim()
    }
  }
  return null
}

function firstNumber(...values) {
  for (const value of values) {
    if (typeof value === 'number' && Number.isFinite(value)) {
      return value
    }
  }
  return null
}

function prettifyModelId(id) {
  const tail = id.includes('/') ? id.slice(id.lastIndexOf('/') + 1) : id
  return tail
    .replace(/[-_]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

function compactNumber(value) {
  return new Intl.NumberFormat('en', {
    notation: 'compact',
    maximumFractionDigits: 1,
  }).format(value)
}

function stripTrailingSlash(value) {
  return value.replace(/\/+$/, '')
}

function normalizeBackendKind(value) {
  const normalized = String(value ?? '')
    .trim()
    .toLowerCase()
  if (['omlx', 'lmstudio', 'openai', 'anthropic', 'claude'].includes(normalized)) {
    return normalized
  }
  return 'lmstudio'
}

function normalizeAuthScheme(value) {
  const normalized = String(value ?? '')
    .trim()
    .toLowerCase()

  if (['auto', 'none', 'bearer', 'x-api-key', 'both'].includes(normalized)) {
    return normalized
  }

  return 'auto'
}

function formatError(error) {
  if (error instanceof Error) {
    return error.message
  }
  return String(error)
}
