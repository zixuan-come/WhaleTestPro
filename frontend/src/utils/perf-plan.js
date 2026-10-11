export const METHODS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS']
const ASSERTIONS = ['json_eq', 'json_contains', 'json_gt', 'json_lt', 'header_eq', 'header_contains', 'response_time_lt', 'json_schema']
const pretty = value => JSON.stringify(value, null, 2)

export function newPerfStep(source = {}) {
  return {
    name: source.name || '请求', method: source.method || 'GET', path: source.url || '/',
    headers: pretty(source.headers || {}), params: pretty(source.params || {}),
    body_type: source.body == null ? 'none' : 'json', body: source.body == null ? '' : pretty(source.body),
    expected_status: '', extract_rules: '{}', assertions: '[]', allow_redirects: false,
  }
}

export function scenarioSteps(scenario, cases, interfaces) {
  if (!scenario?.case_ids?.length) throw new Error('场景没有步骤')
  return scenario.case_ids.map(id => {
    const testCase = cases.find(item => item.id === id)
    const request = interfaces.find(item => item.id === testCase?.interface_id)
    if (!testCase || !request) throw new Error('场景存在已删除或不可访问的用例/接口，不能跳过后压测')
    if (testCase.setup_sql?.length || testCase.teardown_sql?.length || testCase.datasets?.length || testCase.retries > 0) {
      throw new Error('该场景含 SQL、用例级数据集或自动重试，请先制作纯 HTTP 压测场景；不会静默忽略这些配置')
    }
    if ((testCase.assertions || []).some(rule => !ASSERTIONS.includes(rule.type))) {
      throw new Error('场景包含不支持的压测断言（例如 db_eq），请先移除或改为 HTTP 断言')
    }
    return { ...newPerfStep(request), name: testCase.name, expected_status: testCase.expected_status,
      extract_rules: pretty(testCase.extract_rules || {}), assertions: pretty(testCase.assertions || []) }
  })
}

function parse(text, label, shape) {
  let value
  try { value = JSON.parse(text) } catch { throw new Error(`${label}不是合法 JSON`) }
  const isObject = value !== null && typeof value === 'object' && !Array.isArray(value)
  if ((shape === 'object' && !isObject) || (shape === 'array' && !Array.isArray(value))) {
    throw new Error(`${label}必须是 JSON ${shape === 'object' ? '对象' : '数组'}`)
  }
  return value
}

export function buildPerfPlan(form, steps) {
  if (!steps.length || (form.mode === 'single' && steps.length !== 1)) throw new Error('压测步骤数量与模式不符')
  const compiled = steps.map((step, index) => {
    const label = `第 ${index + 1} 步`
    if (!step.name.trim()) throw new Error(`${label}名称不能为空`)
    if (!METHODS.includes(step.method)) throw new Error(`${label}方法不支持`)
    if (!step.path.startsWith('/') || step.path.startsWith('//') || step.path.includes('\\')) throw new Error(`${label}需要相对路径`)
    const headers = parse(step.headers, `${label}请求头`, 'object')
    if (Object.values(headers).some(value => typeof value !== 'string')) throw new Error(`${label}请求头值必须是字符串`)
    const body = step.body_type === 'none' ? null : step.body_type === 'raw' ? step.body : parse(step.body, `${label}请求体`, step.body_type === 'form' ? 'object' : null)
    return { name: step.name.trim(), method: step.method, path: step.path.trim(), headers,
      params: parse(step.params, `${label}参数`, 'object'), body_type: step.body_type, body,
      expected_status: step.expected_status === '' ? null : Number(step.expected_status),
      extract_rules: parse(step.extract_rules, `${label}提取规则`, 'object'),
      assertions: parse(step.assertions, `${label}断言`, 'array'), allow_redirects: step.allow_redirects }
  })
  return { mode: form.mode, steps: compiled, variables: parse(form.variables, '初始变量', 'object'),
    datasets: parse(form.datasets, '数据集', 'array'), stop_on_failure: form.stop_on_failure,
    wait_seconds: Number(form.wait_seconds), timeout_seconds: Number(form.timeout_seconds) }
}
