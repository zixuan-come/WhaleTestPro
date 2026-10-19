import { cloneRequest, requestConfig } from './requestConfig.js'

const requestKeys = ['method', 'url', 'path_params', 'headers', 'params', 'body']
const caseKeys = ['expected_status', 'assertions', 'extract_rules', 'setup_sql', 'teardown_sql', 'datasets', 'retries']
export const stepId = () => globalThis.crypto?.randomUUID?.() || `step-${Date.now()}-${Math.random().toString(36).slice(2)}`

export function caseToStep(testCase, request, key = stepId(), sourceId = null) {
  const name = testCase?.name || `用例 #${sourceId}（已不可用）`
  return {
    step_id: key, source_case_id: testCase?.id ?? sourceId, source_case_name: name,
    interface_id: testCase?.interface_id ?? null, interface_name: request?.name || null, name,
    method: request?.method || null, url: request?.url || null,
    ...requestConfig(request || {}, testCase?.request_overrides),
    ...Object.fromEntries(caseKeys.map(key => [key, cloneRequest(testCase?.[key] ?? null)])),
    expected_status: testCase?.expected_status ?? 200, retries: testCase?.retries || 0,
    missing_reason: !testCase ? '来源用例不存在或不属于当前项目' : !request ? '关联接口不存在或不属于当前项目' : null,
  }
}

export function savedScenarioSteps(scenario, cases, interfaces) {
  if (Array.isArray(scenario.steps)) return cloneRequest(scenario.steps)
  return (scenario.case_ids || []).map(id => {
    const testCase = cases.find(item => item.id === id)
    return caseToStep(testCase, interfaces.find(item => item.id === testCase?.interface_id), stepId(), id)
  })
}

function canonical(value) {
  if (Array.isArray(value)) return value.map(canonical)
  if (value && typeof value === 'object') return Object.fromEntries(Object.keys(value).sort().map(key => [key, canonical(value[key])]))
  return value
}

export function equivalentCaseIds(steps, cases, interfaces) {
  const config = step => JSON.stringify(canonical(Object.fromEntries([...requestKeys, ...caseKeys].map(key => [key, step[key] ?? null]))))
  return new Set(steps.filter(step => {
    const testCase = cases.find(item => item.id === step.source_case_id)
    const request = interfaces.find(item => item.id === testCase?.interface_id)
    return testCase && request && !step.missing_reason && config(step) === config(caseToStep(testCase, request))
  }).map(step => step.source_case_id))
}
