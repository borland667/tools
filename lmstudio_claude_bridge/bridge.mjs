#!/usr/bin/env node

import http from 'node:http'
import { existsSync } from 'node:fs'
import { mkdir, readFile, rename, writeFile } from 'node:fs/promises'
import { homedir } from 'node:os'
import path from 'node:path'
import { Readable } from 'node:stream'
import { pipeline } from 'node:stream/promises'

const LM_STUDIO_BASE_URL = stripTrailingSlash(
  process.env.LMSTUDIO_BASE_URL ?? 'http://127.0.0.1:1234',
)
const BRIDGE_HOST = process.env.CLAUDE_LMSTUDIO_BRIDGE_HOST ?? '127.0.0.1'
const BRIDGE_PORT = Number(process.env.CLAUDE_LMSTUDIO_BRIDGE_PORT ?? '1245')
const MODEL_SYNC_INTERVAL_MS = Number(
  process.env.CLAUDE_LMSTUDIO_MODEL_SYNC_INTERVAL_MS ?? '30000',
)
const REQUEST_TIMEOUT_MS = Number(
  process.env.CLAUDE_LMSTUDIO_REQUEST_TIMEOUT_MS ?? '600000',
)
const MODELS_FIXTURE_FILE = process.env.LMSTUDIO_MODELS_FILE
const LM_STUDIO_API_KEY = process.env.LMSTUDIO_API_KEY ?? ''

const ANTHROPIC_FAMILY_PATTERNS = [
  'claude-',
  'sonnet',
  'opus',
  'haiku',
  'capybara',
]

let lastSyncedOptions = []
let modelSelection = {
  mainModel: null,
  smallModel: null,
}

main().catch(error => {
  console.error(`[bridge] fatal: ${formatError(error)}`)
  process.exitCode = 1
})

async function main() {
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
      await syncModelOptions()
      await startServer()
      return
    default:
      throw new Error(
        `unknown command "${command}". Use "serve", "sync-models", or "print-env".`,
      )
  }
}

function printHelp() {
  console.log(`Claude <-> LM Studio bridge

Usage:
  node bridge.mjs serve
  node bridge.mjs sync-models
  node bridge.mjs print-env

Environment:
  LMSTUDIO_BASE_URL                       LM Studio base URL (default: http://127.0.0.1:1234)
  LMSTUDIO_API_KEY                        Optional LM Studio API key to inject upstream
  CLAUDE_LMSTUDIO_BRIDGE_HOST             Bridge listen host (default: 127.0.0.1)
  CLAUDE_LMSTUDIO_BRIDGE_PORT             Bridge listen port (default: 1245)
  CLAUDE_LMSTUDIO_MODEL_SYNC_INTERVAL_MS  Model sync interval in ms (default: 30000)
  CLAUDE_LMSTUDIO_MAIN_MODEL              Override default mapped main model
  CLAUDE_LMSTUDIO_SMALL_MODEL             Override default mapped small/haiku model
  CLAUDE_LMSTUDIO_MODEL_MAP               JSON object of explicit model rewrites
  CLAUDE_GLOBAL_CONFIG_FILE               Override Claude global config path
  CLAUDE_CONFIG_DIR                       Alternate Claude config root
  LMSTUDIO_MODELS_FILE                    Local JSON fixture for testing model sync`)
}

function printEnvBlock(bridgeBaseUrl) {
  const token =
    process.env.ANTHROPIC_API_KEY ||
    process.env.ANTHROPIC_AUTH_TOKEN ||
    'lmstudio'
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
    `[bridge] listening on http://${BRIDGE_HOST}:${BRIDGE_PORT} -> ${LM_STUDIO_BASE_URL}`,
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
      upstream: LM_STUDIO_BASE_URL,
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

  if (url.pathname.startsWith('/v1/')) {
    return proxyToLmStudio(req, res, url)
  }

  return writeJson(res, 404, {
    error: `unsupported path ${url.pathname}`,
  })
}

async function proxyToLmStudio(req, res, url) {
  const upstreamUrl = new URL(url.pathname + url.search, LM_STUDIO_BASE_URL)
  const headers = copyIncomingHeaders(req.headers)

  let body
  if (req.method && !['GET', 'HEAD'].includes(req.method.toUpperCase())) {
    const rawBody = await readRequestBody(req)
    body = await maybeRewriteRequestBody(url.pathname, rawBody)
  }

  if (LM_STUDIO_API_KEY) {
    headers.set('x-api-key', LM_STUDIO_API_KEY)
  }

  const upstream = await fetch(upstreamUrl, {
    method: req.method,
    headers,
    body,
    signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
  })

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

  await pipeline(Readable.fromWeb(upstream.body), res)
}

async function maybeRewriteRequestBody(pathname, rawBody) {
  if (pathname !== '/v1/messages' || rawBody.length === 0) {
    return rawBody
  }

  let payload
  try {
    payload = JSON.parse(rawBody.toString('utf8'))
  } catch {
    return rawBody
  }

  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    return rawBody
  }

  await syncModelOptions()

  if (typeof payload.model !== 'string' || payload.model.length === 0) {
    return rawBody
  }

  const rewrittenModel = mapRequestedModel(payload.model)
  if (rewrittenModel === payload.model) {
    return rawBody
  }

  console.log(`[bridge] rewrite model "${payload.model}" -> "${rewrittenModel}"`)
  payload.model = rewrittenModel
  return Buffer.from(JSON.stringify(payload), 'utf8')
}

function mapRequestedModel(requestedModel) {
  const explicitMap = parseExplicitModelMap()
  if (explicitMap.has(requestedModel)) {
    return explicitMap.get(requestedModel)
  }

  const normalized = requestedModel.toLowerCase()
  if (explicitMap.has(normalized)) {
    return explicitMap.get(normalized)
  }

  const exact = lastSyncedOptions.find(option => option.value === requestedModel)
  if (exact) {
    return exact.value
  }

  const exactCaseInsensitive = lastSyncedOptions.find(
    option => option.value.toLowerCase() === normalized,
  )
  if (exactCaseInsensitive) {
    return exactCaseInsensitive.value
  }

  if (normalized.includes('haiku')) {
    return modelSelection.smallModel ?? modelSelection.mainModel ?? requestedModel
  }

  if (
    normalized === 'default' ||
    normalized === 'best' ||
    ANTHROPIC_FAMILY_PATTERNS.some(pattern => normalized.includes(pattern))
  ) {
    return modelSelection.mainModel ?? requestedModel
  }

  return requestedModel
}

function parseExplicitModelMap() {
  const raw = process.env.CLAUDE_LMSTUDIO_MODEL_MAP
  if (!raw) {
    return new Map()
  }

  try {
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      return new Map()
    }

    return new Map(
      Object.entries(parsed)
        .filter(([, value]) => typeof value === 'string' && value.length > 0)
        .flatMap(([key, value]) => [
          [key, value],
          [key.toLowerCase(), value],
        ]),
    )
  } catch {
    console.error('[bridge] ignoring invalid CLAUDE_LMSTUDIO_MODEL_MAP JSON')
    return new Map()
  }
}

async function syncModelOptions() {
  const payload = await fetchModelsPayload()
  const options = normalizeModelOptions(payload)
  if (options.length === 0) {
    throw new Error('LM Studio did not return any usable LLM models')
  }

  lastSyncedOptions = options
  modelSelection = chooseDefaultModels(payload, options)

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
  if (MODELS_FIXTURE_FILE) {
    const fixture = await readFile(MODELS_FIXTURE_FILE, 'utf8')
    return JSON.parse(fixture)
  }

  const candidates = ['/api/v1/models', '/v1/models']
  let lastError

  for (const candidate of candidates) {
    try {
      const response = await fetch(new URL(candidate, LM_STUDIO_BASE_URL), {
        headers: buildUpstreamHeaders(),
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

  throw lastError ?? new Error('failed to fetch models from LM Studio')
}

function normalizeModelOptions(payload) {
  const models = coerceModelsArray(payload)
  const optionsById = new Map()

  for (const model of models) {
    const option = normalizeModelOption(model)
    if (!option) {
      continue
    }
    optionsById.set(option.value, option)
  }

  return [...optionsById.values()].sort((a, b) => {
    return a.label.localeCompare(b.label) || a.value.localeCompare(b.value)
  })
}

function normalizeModelOption(model) {
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

  const label =
    firstString(model?.displayName, model?.display_name, model?.name) ??
    prettifyModelId(id)

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
      : `LM Studio model (${id})`

  return {
    value: id,
    label,
    description,
  }
}

function chooseDefaultModels(payload, options) {
  const models = coerceModelsArray(payload)
  const byId = new Map(options.map(option => [option.value, option]))

  const envMain = process.env.CLAUDE_LMSTUDIO_MAIN_MODEL
  const envSmall = process.env.CLAUDE_LMSTUDIO_SMALL_MODEL

  const mainModel =
    (envMain && byId.has(envMain) && envMain) ||
    chooseBestModelId(models, { preferSmall: false }) ||
    options[0]?.value ||
    null

  const smallModel =
    (envSmall && byId.has(envSmall) && envSmall) ||
    chooseBestModelId(models, { preferSmall: true }) ||
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
        firstString(model?.displayName, model?.display_name, model?.name) ?? '',
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
          ) ?? '',
        ),
    }))
    .filter(model => model.id)
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
  if (/(coder|instruct|chat)/i.test(`${model.id} ${model.hint}`)) {
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

function copyIncomingHeaders(headers) {
  const copied = new Headers()

  for (const [key, value] of Object.entries(headers)) {
    if (
      value == null ||
      ['host', 'connection', 'content-length'].includes(key.toLowerCase())
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

function buildUpstreamHeaders() {
  const headers = new Headers()
  if (LM_STUDIO_API_KEY) {
    headers.set('x-api-key', LM_STUDIO_API_KEY)
  }
  return headers
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

  const claudeConfigDir = (
    process.env.CLAUDE_CONFIG_DIR ?? path.join(homedir(), '.claude')
  ).normalize('NFC')
  const legacyPath = path.join(claudeConfigDir, '.config.json')
  if (existsSync(legacyPath)) {
    return legacyPath
  }

  return path.join(process.env.CLAUDE_CONFIG_DIR ?? homedir(), '.claude.json')
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

function formatError(error) {
  if (error instanceof Error) {
    return error.message
  }
  return String(error)
}
