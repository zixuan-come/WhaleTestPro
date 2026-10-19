export const SCENARIO_EXTRACT_OPTIONS = { maxRules: 100, maxNameLength: 64, maxPathLength: 500, reservedNames: ['base_url'] }
export const PERF_EXTRACT_OPTIONS = { maxRules: 50, maxPathLength: 1000, reservedPattern: /^_vu_|^_iteration$/ }

// Keep the API's name → JSONPath mapping; rows are only an editing format.
export function extractRuleRows(value) {
  if (value == null || value === '') return []
  if (typeof value === 'string') {
    try { value = JSON.parse(value) } catch { throw Error('提取规则不是合法 JSON') }
  }
  if (Array.isArray(value)) return value.map(row => ({ name: row.name ?? '', path: row.path ?? '' }))
  if (typeof value !== 'object' || value == null) throw Error('提取规则必须是变量名与表达式的映射')
  return Object.entries(value).map(([name, path]) => ({ name, path }))
}

export function serializeExtractRules(value, options = {}) {
  const { empty = null, label = '提取规则', maxRules, maxNameLength, maxPathLength, reservedNames = [], reservedPattern } = options
  const rows = extractRuleRows(value).filter(row => row.name !== '' || row.path !== '')
  if (maxRules && rows.length > maxRules) throw Error(`${label}最多支持 ${maxRules} 条`)
  const names = new Set(), entries = []
  for (const [index, row] of rows.entries()) {
    const prefix = `${label}第 ${index + 1} 行`
    if (typeof row.name !== 'string' || typeof row.path !== 'string') throw Error(`${prefix}的变量名和表达式必须是文本`)
    const name = row.name.trim(), path = row.path.trim()
    if (!name || !path) throw Error(`${prefix}请同时填写变量名和提取表达式`)
    if (!/^[\p{L}\p{N}_]+$/u.test(name)) throw Error(`${prefix}变量名仅允许字母、数字、下划线`)
    if (maxNameLength && [...name].length > maxNameLength) throw Error(`${prefix}变量名不能超过 ${maxNameLength} 个字符`)
    if (reservedNames.includes(name) || reservedPattern?.test(name)) throw Error(`${prefix}不能使用保留变量名 ${name}`)
    if (maxPathLength && path.length > maxPathLength) throw Error(`${prefix}表达式不能超过 ${maxPathLength} 个字符`)
    if (names.has(name)) throw Error(`${label}变量名 ${name} 重复，请使用不同名称`)
    names.add(name); entries.push([name, path])
  }
  return entries.length ? Object.fromEntries(entries) : empty
}

export function formatExtractValue(value) {
  return typeof value === 'string' ? value === '' ? '""' : value : JSON.stringify(value) ?? '—'
}
