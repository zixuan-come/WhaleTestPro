const clone = value => value === undefined ? undefined : JSON.parse(JSON.stringify(value))
export const ASSERTION_TARGETS = [
  { value: 'json', label: '响应 JSON' }, { value: 'header', label: '响应头' },
  { value: 'time', label: '响应时间' }, { value: 'schema', label: 'JSON Schema' },
  { value: 'database', label: '数据库查询' },
]
export const ASSERTION_OPERATORS = {
  json: [['eq', '等于'], ['contains', '包含'], ['gt', '大于'], ['lt', '小于']],
  header: [['eq', '等于'], ['contains', '包含']], time: [['lt', '小于']],
  schema: [['matches', '符合 Schema']], database: [['eq', '等于']], custom: [['custom', '旧配置']],
}
const TYPES = { json_eq: ['json', 'eq'], json_contains: ['json', 'contains'], json_gt: ['json', 'gt'],
  json_lt: ['json', 'lt'], header_eq: ['header', 'eq'], header_contains: ['header', 'contains'],
  response_time_lt: ['time', 'lt'], json_schema: ['schema', 'matches'], db_eq: ['database', 'eq'] }

export function newAssertionRow(target = '') {
  return { _assertionDraft: true, target, operator: ASSERTION_OPERATORS[target]?.[0][0] || 'eq', path: '',
    expectedType: target === 'time' ? 'number' : target === 'schema' ? 'json' : 'string', expectedText: '', original: null }
}
function expectedType(value) { return value === null ? 'null' : typeof value === 'object' ? 'json' : typeof value }
function expectedText(value) { return typeof value === 'string' ? value : JSON.stringify(value, null, 2) ?? '' }

export function assertionRows(value) {
  if (value == null || value === '') return []
  if (typeof value === 'string') {
    try { value = JSON.parse(value) } catch { throw Error('断言不是合法 JSON') }
  }
  if (!Array.isArray(value)) throw Error('断言必须是数组')
  return value.map(rule => {
    if (!rule || typeof rule !== 'object' || Array.isArray(rule)) throw Error('每条断言必须是对象')
    if (rule._assertionDraft === true) return clone(rule)
    const known = TYPES[rule.type]
    if (!known) return { ...newAssertionRow('custom'), rawText: JSON.stringify(rule, null, 2), original: clone(rule) }
    return { ...newAssertionRow(known[0]), operator: known[1], path: rule.path ?? rule.sql ?? '',
      expectedType: Object.hasOwn(rule, 'expected') ? known[0] === 'schema' ? 'json' : expectedType(rule.expected) : 'missing',
      expectedText: expectedText(rule.expected), original: clone(rule) }
  })
}
export function blankAssertion(row) {
  return !row.target && !row.path && !row.expectedText && !row.rawText && !row.original
}
function parseExpected(row, label) {
  if (row.expectedType === 'string') return row.expectedText
  if (row.expectedType === 'null') return null
  if (row.expectedType === 'boolean') {
    if (!['true', 'false'].includes(row.expectedText)) throw Error(`${label}请选择 true 或 false`)
    return row.expectedText === 'true'
  }
  if (row.expectedType === 'number') {
    const text = row.expectedText.trim()
    // JSON number syntax avoids silently accepting empty input, NaN or Infinity.
    if (!/^-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?$/.test(text) || !Number.isFinite(Number(text))) throw Error(`${label}期望值必须是有效数字`)
    return Number(text)
  }
  if (row.expectedType === 'json') {
    try { return JSON.parse(row.expectedText) } catch { throw Error(`${label}期望值不是合法 JSON`) }
  }
  throw Error(`${label}请选择期望值类型并填写期望值`)
}

export function serializeAssertions(value, { empty = null, label = '断言', allowDatabase = true, strict = false } = {}) {
  const rows = assertionRows(value).filter(row => !blankAssertion(row))
  const rules = rows.map((row, index) => {
    const hint = `${label}第 ${index + 1} 行`
    if (row.target === 'custom') {
      let rule
      try { rule = JSON.parse(row.rawText) } catch { throw Error(`${hint}旧配置不是合法 JSON`) }
      if (!rule || typeof rule !== 'object' || Array.isArray(rule) || typeof rule.type !== 'string' || !rule.type) throw Error(`${hint}旧配置需要有效的断言 type`)
      if (strict && !TYPES[rule.type]) throw Error(`${hint}压测不支持该断言类型`)
      // Known rules edited as legacy JSON still receive the same validation.
      if (TYPES[rule.type]) return serializeAssertions([rule], { label: hint, allowDatabase, strict })[0]
      return rule
    }
    if (!ASSERTION_OPERATORS[row.target]?.some(([key]) => key === row.operator)) throw Error(`${hint}请选择断言对象与判断条件`)
    if (row.target === 'database' && !allowDatabase) throw Error(`${hint}压测不支持数据库断言`)
    const type = Object.keys(TYPES).find(key => TYPES[key][0] === row.target && TYPES[key][1] === row.operator)
    const rule = { ...clone(row.original || {}), type, expected: parseExpected(row, hint) }
    if (['json', 'header', 'database'].includes(row.target)) {
      if (typeof row.path !== 'string' || !row.path.trim()) throw Error(`${hint}请填写${row.target === 'database' ? '查询 SQL' : row.target === 'header' ? '响应头名称' : 'JSONPath 表达式'}`)
      if (row.target === 'database') { delete rule.path; rule.sql = row.path }
      else { delete rule.sql; rule.path = row.path }
    }
    if (row.target === 'time' && strict && (typeof rule.expected !== 'number' || rule.expected <= 0)) throw Error(`${hint}响应时间必须是大于 0 的毫秒数`)
    if (row.target === 'schema' && (rule.expected === null || typeof rule.expected !== 'object' && typeof rule.expected !== 'boolean' || Array.isArray(rule.expected))) throw Error(`${hint}JSON Schema 应为 JSON 对象或布尔值`)
    if (strict && rule.path?.length > 1000) throw Error(`${hint}字段不能超过 1000 个字符`)
    return rule
  })
  return rules.length ? rules : empty
}

export function describeAssertion(rule = {}) {
  const [target, operator] = TYPES[rule.type] || ['custom', 'custom']
  return { target: ASSERTION_TARGETS.find(item => item.value === target)?.label || rule.type || '断言',
    operator: ASSERTION_OPERATORS[target]?.find(([key]) => key === operator)?.[1] || '—',
    path: rule.path || rule.sql || (target === 'time' ? '毫秒' : '—') }
}
export function formatAssertionValue(value) { return value === undefined ? '未记录' : JSON.stringify(value) }
const stable = value => JSON.stringify(value, function (_, item) {
  return item && typeof item === 'object' && !Array.isArray(item)
    ? Object.fromEntries(Object.entries(item).sort(([a], [b]) => a.localeCompare(b))) : item
})
export function matchingAssertionResult(row, index, rules, results) {
  try {
    const rule = serializeAssertions([row])?.[0], saved = rules?.[index], result = results?.[index]
    return rule && saved && result && result.type === rule.type && stable(rule) === stable(saved) ? result : null
  } catch { return null }
}
