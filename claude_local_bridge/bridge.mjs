#!/usr/bin/env node

import http from 'node:http'
import { existsSync, readFileSync } from 'node:fs'
import { mkdir, readFile, rename, writeFile } from 'node:fs/promises'
import { homedir } from 'node:os'
import path from 'node:path'
import { Readable } from 'node:stream'
import { pipeline } from 'node:stream/promises'

const CONFIG_FILE =
  process.env.CLAUDE_LOCAL_CONFIG_FILE ??
  path.resolve(process.cwd(), 'bridge.local.json')
let BRIDGE_CONFIG = loadBridgeConfig(CONFIG_FILE)

const BRIDGE_HOST = normalizeBridgeHost(configValue('bridge.host', process.env.CLAUDE_LOCAL_BRIDGE_HOST))
const BRIDGE_PORT = Number(
  configValue('bridge.port', process.env.CLAUDE_LOCAL_BRIDGE_PORT) ?? '1245',
)

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
let nextRequestId = 1

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

Configuration:
  bridge.local.json                       Preferred runtime settings file in the working directory
  bridge.host / bridge.port               Loopback listen address
  providersFile / providers               Reloadable provider file or inline provider array
  singleProvider                          Legacy one-provider config object
  models.main / models.small              Default Claude-facing model aliases
  models.tool / models.vision             Tool and vision fallback models
  modelSyncIntervalMs                     Model sync interval in ms (default: 30000)
  requestTimeoutMs                        Non-streaming upstream timeout in ms (default: 600000)
  streamRequestTimeoutMs                  Streaming upstream timeout in ms (default: 3600000; 0 disables)
  streamingProgress                       Visible heartbeat settings for timeout-risk streams
  streamingProgress.idleHeartbeatMs       Max quiet period between visible heartbeats (default: 15000; 0 disables)
  thinking.mode                           passthrough-with-progress, passthrough, suppress, status-only
  claudeDesktopModels                     Claude-facing aliases for Desktop/Cowork discovery
  claude.profileName / profileDir         Claude profile under ~/.claude-instances or explicit dir
  claude.globalConfigFile / configDir      Claude config output location for sync-models
  env                                     Config-local env lookup map for apiKeyEnv and print-env

Legacy environment fallback:
  CLAUDE_LOCAL_CONFIG_FILE                JSON bridge config file override
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
  CLAUDE_LOCAL_REQUEST_TIMEOUT_MS         Non-streaming upstream timeout in ms (default: 600000)
  CLAUDE_LOCAL_MAIN_MODEL                 Override default mapped main model
  CLAUDE_LOCAL_SMALL_MODEL                Override default mapped small/haiku model
  CLAUDE_LOCAL_TOOL_MODEL                 Override model used for tool-enabled /v1/messages requests
  CLAUDE_LOCAL_VISION_MODEL               Override model used for image /v1/messages requests
  CLAUDE_LOCAL_STREAM_PROGRESS            Emit visible progress text for timeout-risk streams (default: true)
  CLAUDE_LOCAL_STREAM_PROGRESS_DELAY_MS   Delay before visible progress text (default: 8000)
  CLAUDE_LOCAL_STREAM_PROGRESS_INTERVAL_MS Interval between progress updates (default: 15000)
  CLAUDE_LOCAL_STREAM_PROGRESS_STATUS     Fetch provider status for progress text (default: true)
  CLAUDE_LOCAL_STREAM_PROGRESS_STATUS_TIMEOUT_MS Provider status fetch timeout (default: 1200)
  CLAUDE_LOCAL_THINKING_MODE              Thinking handling: passthrough-with-progress, passthrough, suppress, status-only
  CLAUDE_LOCAL_MODEL_MAP                  JSON object of explicit model rewrites
  CLAUDE_PROFILE_NAME                     Named Claude profile under ~/.claude-instances
  CLAUDE_PROFILE_DIR                      Explicit Claude profile user-data dir
  CLAUDE_GLOBAL_CONFIG_FILE               Override Claude global config path
  CLAUDE_CONFIG_DIR                       Alternate Claude config root
  LMSTUDIO_MODELS_FILE                    LM Studio-specific fixture alias`)
}

function loadBridgeConfig(filePath) {
  if (!filePath || !existsSync(filePath)) {
    if (process.env.CLAUDE_LOCAL_CONFIG_FILE) {
      console.error(`[bridge] config file not found: ${filePath}`)
    }
    return {}
  }

  try {
    const parsed = JSON.parse(readFileSync(filePath, 'utf8'))
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return parsed
    }
    console.error(`[bridge] ignoring ${filePath}: top-level config must be an object`)
  } catch (error) {
    console.error(`[bridge] ignoring invalid config ${filePath}: ${formatError(error)}`)
  }
  return {}
}

function reloadBridgeConfig() {
  BRIDGE_CONFIG = loadBridgeConfig(CONFIG_FILE)
}

function configValue(pathExpression, envValueOverride) {
  const value = pathExpression
    .split('.')
    .reduce((current, key) => current?.[key], BRIDGE_CONFIG)
  if (value === undefined || value === null || value === '') {
    return envValueOverride
  }
  return value
}

function printEnvBlock(bridgeBaseUrl) {
  const token =
    configEnvValue('ANTHROPIC_API_KEY') ||
    configEnvValue('ANTHROPIC_AUTH_TOKEN') ||
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

  scheduleModelSync()
}

function scheduleModelSync() {
  const timeout = setTimeout(() => {
    syncModelOptions().catch(error => {
      console.error(`[bridge] model sync failed: ${formatError(error)}`)
    }).finally(() => {
      scheduleModelSync()
    })
  }, getModelSyncIntervalMs())
  timeout.unref()
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
      providerConfigReloadable: Boolean(getProvidersFile() || CONFIG_FILE),
      bridgeConfigSource: CONFIG_FILE,
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
  const requestId = nextBridgeRequestId()
  const startedAt = Date.now()
  let provider = providers[0]
  let upstreamPath = url.pathname
  const headers = copyIncomingHeaders(req.headers)
  let expectsStreamingResponse = false
  let streamingWarmupMessage = null
  let sseKeepalive = null
  const diagnostics = {
    requestId,
    startedAt,
    method: req.method ?? 'GET',
    path: url.pathname,
    selectedModel: null,
    upstreamModel: null,
    providerId: provider?.id,
    providerLabel: provider?.label ?? provider?.id,
    upstreamPath,
    upstreamStatus: null,
    upstreamContentType: null,
    streamEvents: 0,
    streamBytes: 0,
    visibleEvents: 0,
    progressUpdates: 0,
    lastProgressSummary: null,
    lastProviderStatus: null,
  }

  let body
  if (req.method && !['GET', 'HEAD'].includes(req.method.toUpperCase())) {
    const rawBody = await readRequestBody(req)
    const prepared = await prepareRequestForProvider(url.pathname, rawBody)
    body = prepared.body
    provider = prepared.provider ?? provider
    upstreamPath = prepared.upstreamPath ?? upstreamPath
    expectsStreamingResponse = prepared.expectsStreamingResponse
    streamingWarmupMessage = prepared.streamingWarmupMessage ?? null
    diagnostics.selectedModel = prepared.selectedModel ?? null
    diagnostics.upstreamModel = prepared.upstreamModel ?? streamingWarmupMessage?.model ?? null
  }

  const upstreamUrl = new URL(upstreamPath + url.search, provider.baseUrl)
  diagnostics.providerId = provider?.id
  diagnostics.providerLabel = provider?.label ?? provider?.id
  diagnostics.upstreamPath = upstreamUrl.pathname
  logRequestEvent(diagnostics, 'start', {
    provider: provider?.id,
    upstream: `${upstreamUrl.origin}${upstreamUrl.pathname}`,
    selectedModel: diagnostics.selectedModel,
    upstreamModel: diagnostics.upstreamModel,
    streaming: expectsStreamingResponse,
    timeoutMs: getUpstreamRequestTimeoutMs(expectsStreamingResponse),
  })
  applyUpstreamAuthHeaders(headers, provider)
  if (expectsStreamingResponse) {
    sseKeepalive = startAnthropicSseKeepalive(res, streamingWarmupMessage)
  }

  let upstream
  try {
    upstream = await fetch(upstreamUrl, {
      method: req.method,
      headers,
      body,
      signal: getUpstreamRequestSignal(expectsStreamingResponse),
    })
  } catch (error) {
    console.error(
      `[bridge:${requestId}] upstream request failed for ${provider.id} ${req.method ?? 'GET'} ${upstreamUrl.pathname}: ${formatError(error)}`,
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
  diagnostics.upstreamStatus = upstream.status
  diagnostics.upstreamContentType = upstream.headers.get('content-type')
  logRequestEvent(diagnostics, 'upstream_response', {
    status: upstream.status,
    contentType: diagnostics.upstreamContentType,
  })

  if (
    provider.type === 'openai' &&
    url.pathname === '/v1/messages'
  ) {
    if (expectsStreamingResponse) {
      try {
        return await writeOpenAiChatAsAnthropicSse(upstream, res, provider)
      } finally {
        sseKeepalive?.stop()
      }
    }
    return writeOpenAiChatAsAnthropic(upstream, res, provider)
  }

  if (!upstream.ok && expectsStreamingResponse) {
    sseKeepalive?.stop()
    const text = await upstream.text()
    console.error(
      `[bridge:${requestId}] upstream error from ${provider.id} ${req.method ?? 'GET'} ${upstreamUrl.pathname}: HTTP ${upstream.status} ${truncateForLog(text)}`,
    )
    writeAnthropicSseError(
      res,
      upstream.status,
      `${provider.label} request failed: ${truncateForLog(text)}`,
    )
    return
  }

  if (!upstream.ok && !expectsStreamingResponse) {
    const text = await upstream.text()
    console.error(
      `[bridge:${requestId}] upstream error from ${provider.id} ${req.method ?? 'GET'} ${upstreamUrl.pathname}: HTTP ${upstream.status} ${truncateForLog(text)}`,
    )
    res.statusCode = upstream.status
    res.statusMessage = upstream.statusText
    upstream.headers.forEach((value, key) => {
      if (['content-length', 'connection', 'transfer-encoding'].includes(key)) {
        return
      }
      res.setHeader(key, value)
    })
    res.end(text)
    return
  }

  res.statusCode = upstream.status
  res.statusMessage = upstream.statusText
  if (!res.headersSent) {
    upstream.headers.forEach((value, key) => {
      if (['content-length', 'connection', 'transfer-encoding'].includes(key)) {
        return
      }
      res.setHeader(key, value)
    })
  }

  if (!upstream.body) {
    sseKeepalive?.stop()
    res.end()
    return
  }

  const isSseResponse = isEventStreamContentType(
    upstream.headers.get('content-type'),
  )

  try {
    if (isSseResponse && streamingWarmupMessage) {
      await pipeAnthropicSseAfterWarmup(upstream.body, res, {
        visibleProgress: shouldSendVisibleStreamProgress(),
        provider,
        upstreamModelId: streamingWarmupMessage.model,
        diagnostics,
      })
    } else {
      await pipeline(Readable.fromWeb(upstream.body), res)
    }
    logRequestEvent(diagnostics, 'complete', {
      elapsed: formatDuration((Date.now() - startedAt) / 1000),
      events: diagnostics.streamEvents,
      visibleEvents: diagnostics.visibleEvents,
      progressUpdates: diagnostics.progressUpdates,
    })
  } catch (error) {
    console.error(
      `[bridge:${requestId}] upstream stream failed for ${provider.id} ${req.method ?? 'GET'} ${upstreamUrl.pathname}: ${formatError(error)}; ${formatStreamDiagnostics(diagnostics)}`,
    )
    if (isSseResponse) {
      writeAnthropicSseError(
        res,
        upstream.status || 502,
        buildStreamFailureMessage(provider, error, diagnostics),
      )
      return
    }
    throw error
  } finally {
    sseKeepalive?.stop()
  }
}

function nextBridgeRequestId() {
  const id = nextRequestId
  nextRequestId += 1
  return id.toString(36).padStart(4, '0')
}

function logRequestEvent(diagnostics, event, details = {}) {
  if (!diagnostics) {
    return
  }
  const parts = [
    event,
    `${diagnostics.method} ${diagnostics.path}`,
    details.provider ? `provider=${details.provider}` : null,
    details.upstream ? `upstream=${details.upstream}` : null,
    details.status ? `status=${details.status}` : null,
    details.contentType ? `contentType=${details.contentType}` : null,
    details.selectedModel ? `selected=${details.selectedModel}` : null,
    details.upstreamModel ? `model=${details.upstreamModel}` : null,
    details.streaming != null ? `streaming=${details.streaming}` : null,
    details.timeoutMs != null ? `timeoutMs=${details.timeoutMs}` : null,
    details.elapsed ? `elapsed=${details.elapsed}` : null,
    details.events != null ? `events=${details.events}` : null,
    details.visibleEvents != null ? `visible=${details.visibleEvents}` : null,
    details.progressUpdates != null ? `progress=${details.progressUpdates}` : null,
  ].filter(Boolean)
  console.log(`[bridge:${diagnostics.requestId}] ${parts.join(' ')}`)
}

function formatStreamDiagnostics(diagnostics) {
  if (!diagnostics) {
    return 'no stream diagnostics'
  }
  const elapsed = formatDuration((Date.now() - diagnostics.startedAt) / 1000)
  return compactPhrase([
    `elapsed=${elapsed}`,
    `provider=${diagnostics.providerId ?? 'unknown'}`,
    diagnostics.selectedModel ? `selected=${diagnostics.selectedModel}` : null,
    diagnostics.upstreamModel ? `model=${diagnostics.upstreamModel}` : null,
    diagnostics.upstreamStatus ? `upstreamStatus=${diagnostics.upstreamStatus}` : null,
    `events=${diagnostics.streamEvents}`,
    `bytes=${diagnostics.streamBytes}`,
    `visible=${diagnostics.visibleEvents}`,
    `progress=${diagnostics.progressUpdates}`,
    diagnostics.firstVisibleOutputMs != null
      ? `firstVisible=${formatDuration(diagnostics.firstVisibleOutputMs / 1000)}`
      : null,
    diagnostics.lastProviderStatus
      ? `lastStatus=${diagnostics.lastProviderStatus.phase}:${diagnostics.lastProviderStatus.summary}`
      : null,
  ])
}

function buildStreamFailureMessage(provider, error, diagnostics) {
  const providerLabel = provider?.label ?? provider?.id ?? 'Local provider'
  const model = diagnostics?.upstreamModel ?? 'the selected model'
  const elapsed = diagnostics
    ? formatDuration((Date.now() - diagnostics.startedAt) / 1000)
    : 'unknown time'
  const status = diagnostics?.lastProviderStatus
  const statusText = status?.summary ? ` Last provider status: ${status.summary}.` : ''
  const context = diagnostics
    ? ` Elapsed: ${elapsed}; upstream model: ${model}; stream events: ${diagnostics.streamEvents}; progress updates: ${diagnostics.progressUpdates}.`
    : ''
  return `${providerLabel} stream closed unexpectedly while generating locally.${statusText}${context} Bridge error: ${formatError(error)}`
}

async function prepareRequestForProvider(pathname, rawBody) {
  if (!isAnthropicMessagesPath(pathname) || rawBody.length === 0) {
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

  const isMessagesCreate = pathname === '/v1/messages'
  const expectsStreamingResponse = isMessagesCreate && payload.stream === true
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

  const selectedModel = payload.model
  payload.model = route.upstreamModelId
  if (isMessagesCreate && route.provider.type === 'openai') {
    return {
      provider: route.provider,
      upstreamPath: '/v1/chat/completions',
      body: Buffer.from(JSON.stringify(toOpenAiChatCompletion(payload)), 'utf8'),
      expectsStreamingResponse,
      selectedModel,
      upstreamModel: route.upstreamModelId,
    }
  }

  return {
    provider: route.provider,
    upstreamPath: pathname,
    body: Buffer.from(JSON.stringify(payload), 'utf8'),
    expectsStreamingResponse,
    selectedModel,
    upstreamModel: route.upstreamModelId,
    streamingWarmupMessage: expectsStreamingResponse
      ? anthropicStreamingWarmupMessage(route.upstreamModelId)
      : null,
  }
}

function isAnthropicMessagesPath(pathname) {
  return pathname === '/v1/messages' || pathname.startsWith('/v1/messages/')
}

function resolveModelRoute(requestedModel, payload = null) {
  const normalized = requestedModel.toLowerCase()

  const exact = modelRoutes.get(requestedModel)
  if (exact) {
    return pickCapabilityAwareModel(payload, normalized, exact) ?? exact
  }

  const exactCaseInsensitive = [...modelRoutes.entries()].find(
    ([routeId]) => routeId.toLowerCase() === normalized,
  )
  if (exactCaseInsensitive) {
    const route = exactCaseInsensitive[1]
    return pickCapabilityAwareModel(payload, normalized, route) ?? route
  }

  const explicitMap = parseExplicitModelMap()
  if (explicitMap.has(requestedModel)) {
    const route = routeForTargetModel(explicitMap.get(requestedModel))
    return pickCapabilityAwareModel(payload, normalized, route) ?? route
  }

  const caseInsensitiveMatch = [...explicitMap.entries()].find(
    ([key]) => key.toLowerCase() === normalized,
  )
  if (caseInsensitiveMatch) {
    const route = routeForTargetModel(caseInsensitiveMatch[1])
    return pickCapabilityAwareModel(payload, normalized, route) ?? route
  }

  if (normalized.includes('haiku')) {
    const route = routeForTargetModel(modelSelection.smallModel ?? modelSelection.mainModel)
    return pickCapabilityAwareModel(payload, normalized, route) ?? route
  }

  if (
    normalized === 'default' ||
    normalized === 'best' ||
    ANTHROPIC_FAMILY_PATTERNS.some(pattern => normalized.includes(pattern))
  ) {
    const route = routeForTargetModel(modelSelection.mainModel)
    return pickCapabilityAwareModel(payload, normalized, route) ?? route
  }

  return null
}

function pickCapabilityAwareModel(payload, normalizedRequestedModel, selectedRoute = null) {
  return (
    pickToolAwareModel(payload, normalizedRequestedModel, selectedRoute) ??
    pickVisionAwareModel(payload, normalizedRequestedModel, selectedRoute) ??
    null
  )
}

function pickVisionAwareModel(payload, normalizedRequestedModel, selectedRoute = null) {
  if (!payloadHasImages(payload)) {
    return null
  }

  if (!looksLikeAnthropicAlias(normalizedRequestedModel)) {
    return null
  }

  if (selectedRoute && isVisionCapableRoute(selectedRoute)) {
    return null
  }

  return (
    pickConfiguredModelId(getVisionModelOverride()) ??
    pickDetectedVisionModel() ??
    null
  )
}

function pickToolAwareModel(payload, normalizedRequestedModel, selectedRoute = null) {
  if (!payloadHasTools(payload)) {
    return null
  }

  if (!looksLikeAnthropicAlias(normalizedRequestedModel)) {
    return null
  }

  if (selectedRoute && isToolCapableRoute(selectedRoute)) {
    return null
  }

  return (
    pickConfiguredModelId(getToolModelOverride()) ??
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

function payloadHasImages(payload) {
  if (!payload || typeof payload !== 'object') {
    return false
  }

  for (const message of Array.isArray(payload.messages) ? payload.messages : []) {
    if (contentHasImages(message?.content)) {
      return true
    }
  }

  return contentHasImages(payload.system)
}

function contentHasImages(content) {
  if (!Array.isArray(content)) {
    return false
  }

  for (const part of content) {
    if (!part || typeof part !== 'object') {
      continue
    }
    if (part.type === 'image' || part.type === 'image_url') {
      return true
    }
    if (contentHasImages(part.content)) {
      return true
    }
  }

  return false
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

function pickDetectedVisionModel() {
  const routes = [...modelRoutes.values()]
  const preferred = routes.find(route => isStrongVisionModelId(route))
  if (preferred) {
    return preferred
  }

  return routes.find(route => isVisionCapableRoute(route)) ?? null
}

function isVisionCapableRoute(route) {
  return Boolean(route?.visionCapable || isStrongVisionModelId(route))
}

function isToolCapableRoute(route) {
  return Boolean(route?.toolCapable)
}

function isStrongVisionModelId(route) {
  const text = `${route?.routeId ?? ''} ${route?.upstreamModelId ?? ''}`
  if (/grafted|visualquality|image/i.test(text)) {
    return false
  }
  return /qwen\d*[-.]?vl/i.test(text) || /\bvl\b|vision/i.test(text)
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
      content: openAiContentFromAnthropicContent(message?.content),
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

function openAiContentFromAnthropicContent(content) {
  if (typeof content === 'string') {
    return content
  }
  if (!Array.isArray(content)) {
    return ''
  }

  const parts = []
  for (const part of content) {
    if (typeof part === 'string') {
      parts.push({ type: 'text', text: part })
    } else if (part?.type === 'text' && typeof part.text === 'string') {
      parts.push({ type: 'text', text: part.text })
    } else if (part?.type === 'image' && part.source?.type === 'base64') {
      const mediaType = part.source.media_type ?? 'image/png'
      parts.push({
        type: 'image_url',
        image_url: {
          url: `data:${mediaType};base64,${part.source.data ?? ''}`,
        },
      })
    } else if (part?.type === 'image_url') {
      parts.push(part)
    } else if (part?.type === 'tool_result') {
      const text = anthropicTextFromContent(part.content)
      if (text) {
        parts.push({ type: 'text', text })
      }
    }
  }

  if (parts.length === 0) {
    return ''
  }
  if (parts.every(part => part.type === 'text')) {
    return parts.map(part => part.text).join('\n')
  }
  return parts
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
  const raw = configValue('modelMap', process.env.CLAUDE_LOCAL_MODEL_MAP)
  if (!raw) {
    return new Map()
  }

  try {
    const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
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
      ...(option.maxContextLength ? { max_model_len: option.maxContextLength } : {}),
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
        toolCapable: option.toolCapable,
        visionCapable: option.visionCapable,
        maxContextLength: option.maxContextLength,
      })
    }
  }

  const rawOptions = [...optionsById.values()].sort((a, b) => {
    return a.label.localeCompare(b.label) || a.value.localeCompare(b.value)
  })
  if (rawOptions.length === 0) {
    providerStatuses = nextStatuses
    throw new Error('no configured provider returned any usable LLM models')
  }

  const claudeDesktopOptions = normalizeClaudeDesktopModels(routesById)
  const optionsByPublicId = new Map(rawOptions.map(option => [option.value, option]))
  for (const alias of claudeDesktopOptions) {
    optionsByPublicId.set(alias.value, alias)
    routesById.set(alias.value, alias.route)
  }

  const options = [...optionsByPublicId.values()].sort((a, b) => {
    return a.label.localeCompare(b.label) || a.value.localeCompare(b.value)
  })

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

function normalizeClaudeDesktopModels(routesById) {
  const aliases = configValue('claudeDesktopModels')
  if (!Array.isArray(aliases)) {
    return []
  }

  const options = []
  for (const alias of aliases) {
    if (!alias || typeof alias !== 'object' || Array.isArray(alias)) {
      continue
    }

    const name = firstString(alias.name, alias.id, alias.model)
    const target = firstString(alias.target, alias.route, alias.value)
    if (!name || !target) {
      continue
    }

    const route = routeForTargetModelWithRoutes(routesById, target)
    if (!route) {
      console.error(`[bridge] ignoring Claude desktop model alias "${name}": target "${target}" is not available`)
      continue
    }

    const label =
      firstString(alias.labelOverride, alias.label, alias.displayName) ??
      prettifyModelId(name)
    const description =
      firstString(alias.description) ??
      `${label} -> ${route.provider.id}/${route.upstreamModelId}`

    const option = {
      value: name,
      providerId: route.provider.id,
      upstreamModelId: route.upstreamModelId,
      label,
      description,
      toolCapable: alias.toolCapable === true || route.toolCapable === true,
      visionCapable: alias.visionCapable === true || route.visionCapable === true,
      maxContextLength: firstNumber(alias.maxContextLength, alias.max_model_len) ?? route.maxContextLength,
    }
    Object.defineProperty(option, 'route', {
      enumerable: false,
      value: {
        routeId: name,
        upstreamModelId: route.upstreamModelId,
        provider: route.provider,
        toolCapable: alias.toolCapable === true || route.toolCapable === true,
        visionCapable: alias.visionCapable === true || route.visionCapable === true,
        maxContextLength: option.maxContextLength,
      },
    })
    options.push(option)
  }

  return options.sort((a, b) => {
    return a.label.localeCompare(b.label) || a.value.localeCompare(b.value)
  })
}

function routeForTargetModelWithRoutes(routesById, candidate) {
  if (!candidate) {
    return null
  }

  const exact = routesById.get(candidate)
  if (exact) {
    return exact
  }

  const normalized = candidate.toLowerCase()
  const caseInsensitive = [...routesById.entries()].find(
    ([routeId]) => routeId.toLowerCase() === normalized,
  )
  if (caseInsensitive) {
    return caseInsensitive[1]
  }

  const upstreamMatch = [...routesById.values()].find(
    route => route.upstreamModelId === candidate,
  )
  if (upstreamMatch) {
    return upstreamMatch
  }

  const upstreamCaseInsensitive = [...routesById.values()].find(
    route => route.upstreamModelId.toLowerCase() === normalized,
  )
  return upstreamCaseInsensitive ?? null
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

  const baseLabel =
    firstString(model?.displayName, model?.display_name, model?.name) ??
    prettifyModelId(id)
  const label = provider.labelPrefix
    ? `${provider.labelPrefix}${baseLabel}`
    : `${provider.label}: ${baseLabel}`

  const descriptionParts = []
  const type = firstString(model?.type, model?.model_type, model?.object)
  if (type && type !== 'model') {
    descriptionParts.push(type)
  }
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
    model?.max_model_len,
    model?.maxModelLen,
    model?.context_length,
    model?.contextLength,
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
    isToolCapableModel(model)
  ) {
    descriptionParts.push('tool use')
  }
  if (
    isVisionCapableModel(model, id)
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
    toolCapable: isToolCapableModel(model),
    visionCapable: isVisionCapableModel(model, id),
    maxContextLength,
  }
}

function isToolCapableModel(model) {
  return Boolean(
    model?.trainedForToolUse === true ||
      model?.capabilities?.trained_for_tool_use === true ||
      model?.toolCapable === true ||
      model?.capabilities?.tool_use === true,
  )
}

function isVisionCapableModel(model, id) {
  if (model?.vision === true || model?.capabilities?.vision === true) {
    return true
  }

  return isStrongVisionModelId({ routeId: id, upstreamModelId: id })
}

function chooseDefaultModels(options) {
  const byId = new Map(options.map(option => [option.value, option]))

  const envMain = configValue('models.main', process.env.CLAUDE_LOCAL_MAIN_MODEL)
  const envSmall = configValue('models.small', process.env.CLAUDE_LOCAL_SMALL_MODEL)

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
  reloadBridgeConfig()
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
  const filePath = getProvidersFile()
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
  const raw = configValue('providers', process.env.CLAUDE_LOCAL_PROVIDERS)
  if (!raw) {
    return []
  }

  if (Array.isArray(raw) || (raw && typeof raw === 'object')) {
    return parseProvidersJson(JSON.stringify(raw), 'bridge config providers')
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
    configValue('singleProvider.backend', process.env.CLAUDE_LOCAL_INFERENCE_BACKEND) ??
      (configEnvValue('OMLX_BASE_URL') ? 'omlx' : 'lmstudio'),
  )
  const baseUrl = stripTrailingSlash(
    configValue('singleProvider.baseUrl', process.env.CLAUDE_LOCAL_INFERENCE_BASE_URL) ??
      (backend === 'omlx'
        ? configEnvValue('OMLX_BASE_URL') ?? 'http://127.0.0.1:8000'
        : backend === 'openai'
          ? configEnvValue('OPENAI_BASE_URL') ?? 'https://api.openai.com'
          : backend === 'anthropic' || backend === 'claude'
            ? configEnvValue('ANTHROPIC_BASE_URL') ?? 'https://api.anthropic.com'
            : configEnvValue('LMSTUDIO_BASE_URL') ?? 'http://127.0.0.1:1234'),
  )
  return {
    id: backend,
    type: backend === 'openai' ? 'openai' : 'anthropic',
    baseUrl,
    apiKey:
      configValue('singleProvider.apiKey', process.env.CLAUDE_LOCAL_INFERENCE_API_KEY) ??
      (backend === 'omlx'
        ? configEnvValue('OMLX_API_KEY') ?? ''
        : backend === 'openai'
          ? configEnvValue('OPENAI_API_KEY') ?? ''
          : backend === 'anthropic' || backend === 'claude'
            ? configEnvValue('ANTHROPIC_API_KEY') ?? ''
            : configEnvValue('LMSTUDIO_API_KEY') ?? ''),
    authScheme: configValue('singleProvider.authScheme', process.env.CLAUDE_LOCAL_INFERENCE_AUTH_SCHEME) ?? 'auto',
    modelsFile:
      configValue('singleProvider.modelsFile', process.env.CLAUDE_LOCAL_INFERENCE_MODELS_FILE) ??
      configEnvValue('LMSTUDIO_MODELS_FILE'),
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
  return configEnvValue(name.trim()) ?? ''
}

function configEnvValue(name) {
  return BRIDGE_CONFIG.env?.[name] ?? process.env[name]
}

function getProvidersFile() {
  return configValue('providersFile', process.env.CLAUDE_LOCAL_PROVIDERS_FILE)
}

function getToolModelOverride() {
  return configValue('models.tool', process.env.CLAUDE_LOCAL_TOOL_MODEL) ?? ''
}

function getVisionModelOverride() {
  return configValue('models.vision', process.env.CLAUDE_LOCAL_VISION_MODEL) ?? ''
}

function getModelSyncIntervalMs() {
  return Number(
    configValue('modelSyncIntervalMs', process.env.CLAUDE_LOCAL_MODEL_SYNC_INTERVAL_MS) ??
      '30000',
  )
}

function getRequestTimeoutMs() {
  return Number(
    configValue('requestTimeoutMs', process.env.CLAUDE_LOCAL_REQUEST_TIMEOUT_MS) ??
      '600000',
  )
}

function getStreamRequestTimeoutMs() {
  return Number(
    configValue('streamRequestTimeoutMs') ??
      '3600000',
  )
}

function getUpstreamRequestTimeoutMs(expectsStreamingResponse) {
  return expectsStreamingResponse ? getStreamRequestTimeoutMs() : getRequestTimeoutMs()
}

function getUpstreamRequestSignal(expectsStreamingResponse) {
  const timeoutMs = getUpstreamRequestTimeoutMs(expectsStreamingResponse)
  if (!Number.isFinite(timeoutMs) || timeoutMs <= 0) {
    return undefined
  }
  return AbortSignal.timeout(timeoutMs)
}

function shouldSendVisibleStreamProgress() {
  return parseBoolean(
    configValue('streamingProgress.enabled', process.env.CLAUDE_LOCAL_STREAM_PROGRESS),
    true,
  )
}

function getVisibleStreamProgressDelayMs() {
  return Number(
    configValue('streamingProgress.delayMs', process.env.CLAUDE_LOCAL_STREAM_PROGRESS_DELAY_MS) ??
      '8000',
  )
}

function getVisibleStreamProgressIntervalMs() {
  return Number(
    configValue('streamingProgress.intervalMs', process.env.CLAUDE_LOCAL_STREAM_PROGRESS_INTERVAL_MS) ??
      '15000',
  )
}

function getVisibleStreamProgressIdleHeartbeatMs() {
  return Number(
    configValue('streamingProgress.idleHeartbeatMs') ??
      '15000',
  )
}

function shouldFetchVisibleStreamProgressStatus() {
  return parseBoolean(
    configValue('streamingProgress.providerStatusEnabled', process.env.CLAUDE_LOCAL_STREAM_PROGRESS_STATUS),
    true,
  )
}

function getVisibleStreamProgressStatusTimeoutMs() {
  return Number(
    configValue(
      'streamingProgress.providerStatusTimeoutMs',
      process.env.CLAUDE_LOCAL_STREAM_PROGRESS_STATUS_TIMEOUT_MS,
    ) ?? '1200',
  )
}

function getThinkingMode() {
  const raw = String(
    configValue('thinking.mode', process.env.CLAUDE_LOCAL_THINKING_MODE) ??
      'passthrough-with-progress',
  )
    .trim()
    .toLowerCase()
  if (['passthrough', 'pass-through', 'show', 'on', 'true'].includes(raw)) {
    return 'passthrough'
  }
  if (['passthrough-with-progress', 'pass-through-with-progress'].includes(raw)) {
    return 'passthrough-with-progress'
  }
  if (['suppress', 'off', 'false', 'hidden'].includes(raw)) {
    return 'suppress'
  }
  if (['status-only', 'status'].includes(raw)) {
    return 'status-only'
  }
  console.error(`[bridge] unknown thinking.mode "${raw}", using passthrough-with-progress`)
  return 'passthrough-with-progress'
}

function shouldPassthroughThinking(mode) {
  return mode === 'passthrough' || mode === 'passthrough-with-progress'
}

function parseBoolean(value, defaultValue = false) {
  if (value === undefined || value === null || value === '') {
    return defaultValue
  }
  if (typeof value === 'boolean') {
    return value
  }
  const normalized = String(value).trim().toLowerCase()
  if (['1', 'true', 'yes', 'on'].includes(normalized)) {
    return true
  }
  if (['0', 'false', 'no', 'off'].includes(normalized)) {
    return false
  }
  return defaultValue
}

function providerConfigSource() {
  const providersFile = getProvidersFile()
  if (providersFile) {
    return providersFile
  }
  if (BRIDGE_CONFIG.providers) {
    return 'bridge config providers'
  }
  if (process.env.CLAUDE_LOCAL_PROVIDERS) {
    return 'legacy CLAUDE_LOCAL_PROVIDERS'
  }
  return 'single-provider fallback'
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
  if (!process.env.CLAUDE_LOCAL_PROVIDERS && !getProvidersFile() && !BRIDGE_CONFIG.providers && providers.length === 1) {
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

function anthropicStreamingWarmupMessage(model) {
  return {
    id: `msg_bridge_warmup_${Date.now().toString(36)}`,
    type: 'message',
    role: 'assistant',
    model,
    content: [],
    stop_reason: null,
    stop_sequence: null,
    usage: {
      input_tokens: 0,
      output_tokens: 0,
    },
  }
}

function startAnthropicSseKeepalive(res, warmupMessage = null) {
  if (!res.headersSent) {
    res.statusCode = 200
    res.setHeader('content-type', 'text/event-stream; charset=utf-8')
    res.setHeader('cache-control', 'no-cache')
    res.setHeader('connection', 'keep-alive')
  }

  if (warmupMessage) {
    writeAnthropicSseEvent(res, 'message_start', {
      type: 'message_start',
      message: warmupMessage,
    })
  } else {
    writeAnthropicSsePing(res)
  }

  const interval = setInterval(() => {
    writeAnthropicSsePing(res)
  }, 5000)
  interval.unref?.()

  const stop = () => {
    clearInterval(interval)
  }
  res.once('close', stop)
  return { stop }
}

function writeAnthropicSsePing(res) {
  writeAnthropicSseEvent(res, 'ping', { type: 'ping' })
}

function writeAnthropicSseEvent(res, event, payload) {
  if (res.writableEnded || res.destroyed) {
    return
  }
  res.write(`event: ${event}\ndata: ${JSON.stringify(payload)}\n\n`)
}

async function pipeAnthropicSseAfterWarmup(upstreamBody, res, options = {}) {
  const reader = upstreamBody.getReader()
  const decoder = new TextDecoder()
  const startedAt = Date.now()
  const diagnostics = options.diagnostics
  let buffer = ''
  let skippedMessageStart = false
  let progressStarted = false
  let progressClosed = false
  let sawVisibleOutput = false
  let progressUpdateInFlight = false
  let lastProgressKey = ''
  const skippedThinkingIndexes = new Set()

  const progressDelayMs = getVisibleStreamProgressDelayMs()
  const progressIntervalMs = getVisibleStreamProgressIntervalMs()
  const progressIdleHeartbeatMs = getVisibleStreamProgressIdleHeartbeatMs()
  const thinkingMode = getThinkingMode()
  const visibleProgressEnabled = options.visibleProgress && thinkingMode !== 'passthrough'
  let progressInterval = null
  const writeProgressUpdate = async ({ initial = false } = {}) => {
    if (
      progressClosed ||
      sawVisibleOutput ||
      progressUpdateInFlight ||
      res.writableEnded ||
      res.destroyed
    ) {
      return
    }

    progressUpdateInFlight = true
    try {
      const progress = await buildVisibleProgressText({
        provider: options.provider,
        upstreamModelId: options.upstreamModelId,
        elapsedMs: Date.now() - startedAt,
        initial,
      })
      if (diagnostics && progress?.status) {
        diagnostics.lastProviderStatus = progress.status
        diagnostics.lastProgressSummary = progress.status.summary
      }
      const now = Date.now()
      const sameProgressKey = progress.key === lastProgressKey
      const canSendIdleHeartbeat =
        sameProgressKey &&
        Number.isFinite(progressIdleHeartbeatMs) &&
        progressIdleHeartbeatMs > 0 &&
        diagnostics?.lastProgressUpdateAt != null &&
        now - diagnostics.lastProgressUpdateAt >= progressIdleHeartbeatMs

      if (
        !progress?.text ||
        (sameProgressKey && !canSendIdleHeartbeat) ||
        progressClosed ||
        sawVisibleOutput ||
        res.writableEnded ||
        res.destroyed
      ) {
        return
      }
      lastProgressKey = progress.key
      if (diagnostics) {
        diagnostics.progressUpdates += 1
        diagnostics.lastProgressUpdateAt = now
      }
      writeAnthropicSseEvent(res, 'content_block_delta', {
        type: 'content_block_delta',
        index: 0,
        delta: {
          type: 'text_delta',
          text: progress.text,
        },
      })
    } finally {
      progressUpdateInFlight = false
    }
  }
  const startProgress = () => {
    if (
      !visibleProgressEnabled ||
      progressStarted ||
      progressClosed ||
      sawVisibleOutput ||
      res.writableEnded ||
      res.destroyed
    ) {
      return
    }
    progressStarted = true
    writeAnthropicSseEvent(res, 'content_block_start', {
      type: 'content_block_start',
      index: 0,
      content_block: { type: 'text', text: '' },
    })
    void writeProgressUpdate({ initial: true })
    progressInterval = setInterval(() => {
      void writeProgressUpdate()
    }, progressIntervalMs)
    progressInterval.unref?.()
  }
  const closeProgress = () => {
    if (progressClosed) {
      return
    }
    progressClosed = true
    if (progressInterval) {
      clearInterval(progressInterval)
      progressInterval = null
    }
    if (progressStarted && !res.writableEnded && !res.destroyed) {
      writeAnthropicSseEvent(res, 'content_block_stop', {
        type: 'content_block_stop',
        index: 0,
      })
    }
  }
  const progressTimeout = visibleProgressEnabled
    ? setTimeout(startProgress, progressDelayMs)
    : null
  progressTimeout?.unref?.()

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) {
        break
      }
      if (diagnostics) {
        diagnostics.streamBytes += value.byteLength ?? 0
      }
      buffer += decoder.decode(value, { stream: true })
      const events = buffer.split(/\r?\n\r?\n/)
      buffer = events.pop() ?? ''
      for (const event of events) {
        if (diagnostics) {
          diagnostics.streamEvents += 1
        }
        if (!skippedMessageStart && isSseEvent(event, 'message_start')) {
          skippedMessageStart = true
          continue
        }
        const nextEvent = transformAnthropicSseEventAfterWarmup(event, {
          progressStarted,
          skippedThinkingIndexes,
          thinkingMode,
        })
        if (nextEvent.skip) {
          continue
        }
        if (nextEvent.visibleOutput) {
          if (diagnostics) {
            diagnostics.visibleEvents += 1
            diagnostics.firstVisibleOutputMs ??= Date.now() - diagnostics.startedAt
          }
          sawVisibleOutput = true
          closeProgress()
        }
        if (!res.writableEnded && !res.destroyed) {
          res.write(`${nextEvent.block}\n\n`)
        }
      }
    }
    buffer += decoder.decode()
    if (buffer && !( !skippedMessageStart && isSseEvent(buffer, 'message_start'))) {
      const nextEvent = transformAnthropicSseEventAfterWarmup(buffer, {
        progressStarted,
        skippedThinkingIndexes,
        thinkingMode,
      })
      if (!nextEvent.skip) {
        if (nextEvent.visibleOutput) {
          if (diagnostics) {
            diagnostics.visibleEvents += 1
            diagnostics.firstVisibleOutputMs ??= Date.now() - diagnostics.startedAt
          }
          closeProgress()
        }
        res.write(nextEvent.block)
      }
    }
    closeProgress()
    res.end()
  } finally {
    if (progressTimeout) {
      clearTimeout(progressTimeout)
    }
    closeProgress()
    reader.releaseLock()
  }
}

async function buildVisibleProgressText({
  provider,
  upstreamModelId,
  elapsedMs,
  initial = false,
}) {
  const elapsed = formatDuration(Math.max(0, elapsedMs / 1000))
  const providerStatus = await getProviderProgressStatus(provider, upstreamModelId)
  if (providerStatus) {
    return {
      key: providerStatus.key,
      status: providerStatus,
      text: initial
        ? formatInitialProgressBlock({
            elapsed,
            status: providerStatus,
          })
        : formatProgressUpdate({ elapsed, status: providerStatus }),
    }
  }

  const key = `generic:${Math.floor(elapsedMs / 30000)}`
  return {
    key,
    status: {
      phase: 'generic',
      title: initial ? 'Waiting for visible output' : 'Still waiting for visible output',
      lines: [],
      summary: `waiting ${elapsed} for visible model output`,
    },
    text: initial
      ? formatInitialProgressBlock({
          elapsed,
          status: {
            title: 'Waiting for visible output',
            lines: [`Elapsed: ${elapsed}`, 'The provider is connected but has not emitted answer text yet.'],
            summary: `waiting ${elapsed} for visible model output`,
          },
        })
      : formatProgressUpdate({
          elapsed,
          status: {
            title: 'Still waiting for visible output',
            lines: [],
            summary: `waiting ${elapsed} for visible model output`,
          },
        }),
  }
}

function formatInitialProgressBlock({
  elapsed,
  status,
}) {
  return `\n\n_Local model: ${status.summary} (${elapsed})._`
}

function formatProgressUpdate({ elapsed, status }) {
  return `\n\n_Local model: ${status.summary} (${elapsed})._`
}

async function getProviderProgressStatus(provider, upstreamModelId) {
  if (!shouldFetchVisibleStreamProgressStatus() || !provider) {
    return null
  }

  if (provider.backend === 'omlx' || provider.id === 'omlx') {
    return getOmlxProgressStatus(provider, upstreamModelId)
  }

  return null
}

async function getOmlxProgressStatus(provider, upstreamModelId) {
  const payload = await fetchJsonBestEffort(
    new URL('/admin/api/activity', provider.baseUrl),
    provider,
    getVisibleStreamProgressStatusTimeoutMs(),
  )
  const activeModels = payload?.active_models
  if (!activeModels || typeof activeModels !== 'object') {
    return null
  }

  const models = Array.isArray(activeModels.models) ? activeModels.models : []
  const model =
    models.find(item => item?.id === upstreamModelId) ??
    models.find(item => item?.id?.toLowerCase?.() === upstreamModelId?.toLowerCase?.())

  if (!model) {
    const active = Number(activeModels.total_active_requests ?? 0)
    const waiting = Number(activeModels.total_waiting_requests ?? 0)
    return progressStatus({
      phase: 'activity',
      bucket: `${active}:${waiting}`,
      title: 'Waiting for model activity',
      lines: [],
      summary: compactPhrase([
        active > 0 ? `${active} active request${active === 1 ? '' : 's'}` : null,
        waiting > 0 ? `${waiting} waiting` : null,
        'waiting for model activity',
      ]),
    })
  }

  if (model.is_loading) {
    const elapsed = model.loading_elapsed_seconds != null
      ? formatDuration(model.loading_elapsed_seconds)
      : null
    const remaining = model.loading_remaining_seconds_estimate != null
      ? formatDuration(model.loading_remaining_seconds_estimate)
      : null
    return progressStatus({
      phase: 'loading',
      bucket: bucketNumber(model.loading_elapsed_seconds, 10),
      title: 'OMLX is loading the model',
      lines: [],
      summary: compactPhrase([
        'loading model',
        elapsed ? `${elapsed} elapsed` : null,
        remaining ? `about ${remaining} left` : null,
      ]),
    })
  }

  const prefilling = Array.isArray(model.prefilling) ? model.prefilling : []
  const generating = Array.isArray(model.generating) ? model.generating : []
  const waiting = Array.isArray(model.waiting) ? model.waiting : []

  if (prefilling.length > 0) {
    const current = prefilling[0]
    const processed = Number(current.processed ?? 0)
    const total = Number(current.total ?? 0)
    const percent = total > 0 ? Math.floor((processed / total) * 100) : null
    const progress = `${formatTokenCount(processed)}${total > 0 ? ` / ${formatTokenCount(total)}` : ''} tokens`
    const speed = current.speed ? `${formatNumber(current.speed, 1)} tok/s` : null
    const eta = current.eta ? `about ${formatDuration(current.eta)} left` : null
    return progressStatus({
      phase: 'prefill',
      bucket: total > 0 ? Math.floor((processed / total) * 4) : bucketNumber(processed, 8000),
      title: 'OMLX is prefilling the prompt',
      lines: [],
      summary: compactPhrase([
        `prefill ${progress}${percent != null ? ` (${percent}%)` : ''}`,
        eta,
      ]),
    })
  }

  if (generating.length > 0) {
    const current = generating[0]
    const generated = formatTokenCount(current.generated_tokens ?? 0)
    const speed = current.tokens_per_second != null
      ? `${formatNumber(current.tokens_per_second, 2)} tok/s`
      : null
    const lastToken = current.last_activity_age_seconds != null
      ? `${formatDuration(current.last_activity_age_seconds)} ago`
      : null
    return progressStatus({
      phase: 'generate',
      bucket: `${bucketNumber(current.generated_tokens, 10)}:${bucketNumber(current.last_activity_age_seconds, 15)}`,
      title: 'OMLX is generating',
      lines: [],
      summary: compactPhrase([
        `generating ${generated} tokens`,
        speed,
        lastToken ? `last token ${lastToken}` : null,
      ]),
    })
  }

  if (waiting.length > 0 || Number(model.waiting_requests ?? 0) > 0) {
    const position = waiting[0]?.queue_position
    return progressStatus({
      phase: 'queued',
      bucket: `${position ?? 'unknown'}:${model.waiting_requests ?? 0}`,
      title: 'OMLX queued this request',
      lines: [],
      summary: compactPhrase([
        'queued',
        position ? `position ${position}` : null,
        model.waiting_requests ? `${model.waiting_requests} waiting` : null,
      ]),
    })
  }

  return progressStatus({
    phase: 'loaded-waiting',
    bucket: bucketNumber(activeModels.model_memory_used, 5 * 1024 ** 3),
    title: 'Model loaded, waiting for answer text',
    lines: [],
    summary: compactPhrase([
      'model loaded, waiting for output',
    ]),
  })
}

async function fetchJsonBestEffort(url, provider, timeoutMs) {
  try {
    const headers = new Headers()
    applyUpstreamAuthHeaders(headers, provider)
    const response = await fetch(url, {
      headers,
      signal: AbortSignal.timeout(timeoutMs),
    })
    if (!response.ok) {
      return null
    }
    return response.json()
  } catch {
    return null
  }
}

function progressStatus({ phase, bucket, title, lines, summary }) {
  return {
    key: `${phase}:${bucket}`,
    phase,
    title,
    lines,
    summary,
  }
}

function bucketNumber(value, bucketSize) {
  const number = Number(value)
  if (!Number.isFinite(number)) {
    return 'unknown'
  }
  return Math.floor(number / bucketSize)
}

function compactPhrase(parts) {
  return parts.filter(Boolean).join(', ')
}

function displayModelName(modelId) {
  return String(modelId ?? 'the selected model')
    .replace(/^omlx\//, '')
    .replace(/-/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

function formatTokenCount(value) {
  const number = Number(value)
  if (!Number.isFinite(number)) {
    return '0'
  }
  if (Math.abs(number) >= 1_000_000) {
    return `${formatNumber(number / 1_000_000, 1)}M`
  }
  if (Math.abs(number) >= 1_000) {
    return `${formatNumber(number / 1_000, 1)}k`
  }
  return String(Math.round(number))
}

function formatDuration(seconds) {
  const number = Number(seconds)
  if (!Number.isFinite(number) || number < 0) {
    return '0s'
  }
  if (number < 1) {
    return `${formatNumber(number, 1)}s`
  }
  if (number < 60) {
    return `${Math.round(number)}s`
  }
  const minutes = Math.floor(number / 60)
  const remainingSeconds = Math.round(number % 60)
  if (minutes < 60) {
    return `${minutes}m ${remainingSeconds}s`
  }
  const hours = Math.floor(minutes / 60)
  return `${hours}h ${minutes % 60}m`
}

function formatNumber(value, digits = 0) {
  const number = Number(value)
  if (!Number.isFinite(number)) {
    return '0'
  }
  return number.toFixed(digits).replace(/\.0+$/, '')
}

function transformAnthropicSseEventAfterWarmup(block, state) {
  const eventName = sseEventName(block)
  const data = sseEventData(block)
  if (!data) {
    return { block, skip: false, visibleOutput: false }
  }

  let payload
  try {
    payload = JSON.parse(data)
  } catch {
    return { block, skip: false, visibleOutput: false }
  }

  const index = Number(payload.index)
  if (
    eventName === 'content_block_start' &&
    payload.content_block?.type === 'thinking' &&
    Number.isInteger(index)
  ) {
    if (!shouldPassthroughThinking(state.thinkingMode)) {
      state.skippedThinkingIndexes.add(index)
      return { block, skip: true, visibleOutput: false }
    }
  }

  if (
    Number.isInteger(index) &&
    state.skippedThinkingIndexes.has(index) &&
    (eventName === 'content_block_delta' || eventName === 'content_block_stop')
  ) {
    return { block, skip: true, visibleOutput: false }
  }

  const visibleOutput =
    payload.content_block?.type === 'text' ||
    payload.content_block?.type === 'thinking' ||
    payload.content_block?.type === 'tool_use' ||
    payload.delta?.type === 'text_delta' ||
    payload.delta?.type === 'thinking_delta' ||
    payload.delta?.type === 'signature_delta' ||
    payload.delta?.type === 'input_json_delta'

  if (state.progressStarted && Number.isInteger(index)) {
    payload.index = visibleContentIndexAfterWarmup(index, state.skippedThinkingIndexes)
    return {
      block: replaceSseData(block, payload),
      skip: false,
      visibleOutput,
    }
  }

  return { block, skip: false, visibleOutput }
}

function visibleContentIndexAfterWarmup(index, skippedThinkingIndexes) {
  const skippedBefore = [...skippedThinkingIndexes].filter(skipped => skipped < index).length
  return index - skippedBefore + 1
}

function isSseEvent(block, eventName) {
  return block
    .split(/\r?\n/)
    .some(line => line.trim() === `event: ${eventName}`)
}

function sseEventName(block) {
  const line = block
    .split(/\r?\n/)
    .find(line => line.startsWith('event:'))
  return line ? line.slice('event:'.length).trim() : ''
}

function sseEventData(block) {
  const lines = block
    .split(/\r?\n/)
    .filter(line => line.startsWith('data:'))
    .map(line => line.slice('data:'.length).trimStart())
  return lines.length > 0 ? lines.join('\n') : ''
}

function replaceSseData(block, payload) {
  return block
    .split(/\r?\n/)
    .map(line => line.startsWith('data:')
      ? `data: ${JSON.stringify(payload)}`
      : line)
    .join('\n')
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
  const explicitGlobalConfig = configValue(
    'claude.globalConfigFile',
    process.env.CLAUDE_GLOBAL_CONFIG_FILE,
  )
  if (explicitGlobalConfig) {
    return explicitGlobalConfig
  }

  const profileDir = getClaudeProfileDir()
  if (profileDir) {
    const profileLegacyPath = path.join(profileDir, '.config.json')
    if (existsSync(profileLegacyPath)) {
      return profileLegacyPath
    }
    return path.join(profileDir, '.claude.json')
  }

  const configuredConfigDir = configValue(
    'claude.configDir',
    process.env.CLAUDE_CONFIG_DIR,
  )
  const claudeConfigDir = (configuredConfigDir ?? path.join(homedir(), '.claude')).normalize('NFC')
  const legacyPath = path.join(claudeConfigDir, '.config.json')
  if (existsSync(legacyPath)) {
    return legacyPath
  }

  return path.join(configuredConfigDir ?? homedir(), '.claude.json')
}

function getClaudeProfileDir() {
  const explicitProfileDir = configValue('claude.profileDir', process.env.CLAUDE_PROFILE_DIR)
  if (explicitProfileDir) {
    return explicitProfileDir
  }

  const profileName = firstString(
    configValue('claude.profileName', process.env.CLAUDE_PROFILE_NAME),
  )
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

function truncateForLog(value, maxLength = 800) {
  const text = String(value ?? '').replace(/\s+/g, ' ').trim()
  if (text.length <= maxLength) {
    return text
  }
  return `${text.slice(0, maxLength)}...`
}
