function failureReason(value) {
  if (Array.isArray(value)) {
    const failed = value.find(item => item.passed === false || item.error)
    return failed ? failureReason(failed) : ''
  }
  if (!value || typeof value !== 'object') return ''
  if (value.error || value.teardown_error) return value.error || value.teardown_error
  if (value.actual_status != null && value.expected_status != null && value.actual_status !== value.expected_status) return `期望状态码 ${value.expected_status}，实际 ${value.actual_status}`
  const assertion = Array.isArray(value.assertions) && value.assertions.find(item => !item.passed)
  if (assertion) return '断言未通过，请查看完整报告中的断言明细'
  if (value.detail) return failureReason(value.detail)
  return ''
}

export function regressionRows(results, suiteName = '') {
  return results.flatMap(item => {
    if (item.type === 'suite' && item.detail?.results?.length) return regressionRows(item.detail.results, item.name)
    return [{ name: item.name || item.case_name || '名称未记录', passed: !!item.passed, suite_name: suiteName,
      reason: failureReason(item) || (item.passed ? '' : '执行未通过，请查看完整报告') }]
  })
}
