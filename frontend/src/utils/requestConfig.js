import { pathParameterNames, pathParameterValues } from './pathParameters.js'

export const cloneRequest = value => JSON.parse(JSON.stringify(value))

export function requestConfig(interfaceData = {}, overrides = null) {
  const base = Object.fromEntries(['path_params', 'headers', 'params', 'body'].map(key => [key, interfaceData[key] ?? null]))
  return cloneRequest({ ...base, ...(overrides || {}) })
}

function rows(value) {
  return Object.entries(value || {}).map(([key, value]) => ({ enabled: true, key, value: value == null ? '' : String(value) }))
}

export function requestDraft(config = {}) {
  return {
    pathParams: cloneRequest(config.path_params || {}), headers: rows(config.headers), params: rows(config.params),
    bodyType: config.body == null ? 'none' : 'json', body: config.body == null ? '' : JSON.stringify(config.body, null, 2),
  }
}

function invalid(message, tab) {
  const error = new Error(message)
  error.tab = tab
  throw error
}

function dictionary(rows, tab, label) {
  const entries = [], seen = new Set()
  for (const row of rows) {
    if (!row.enabled) continue
    const key = row.key.trim(), value = String(row.value ?? '')
    if (!key && !value.trim()) continue
    if (!key) invalid(label + ' 缺少参数名', tab)
    const unique = tab === 'headers' ? key.toLowerCase() : key
    if (seen.has(unique)) invalid(label + ' 参数名重复：' + key, tab)
    seen.add(unique)
    entries.push([key, value])
  }
  return entries.length ? Object.fromEntries(entries) : null
}

export function serializeRequest(draft, url, { requirePath = true } = {}) {
  const path = pathParameterValues(url, draft.pathParams)
  const missing = pathParameterNames(url).filter(key => !String(path[key]).trim())
  if (requirePath && missing.length) invalid('请填写路径参数：' + missing.join('、'), 'path')
  let body = null
  if (draft.bodyType === 'json') {
    try { body = JSON.parse(draft.body) } catch { invalid('Body 不是合法 JSON', 'body') }
    if (!body || Array.isArray(body) || typeof body !== 'object') invalid('Body 当前仅支持 JSON 对象', 'body')
  }
  return { path_params: path, headers: dictionary(draft.headers, 'headers', 'Headers'), params: dictionary(draft.params, 'params', 'Query'), body }
}
