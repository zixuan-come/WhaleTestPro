export const REPORT_TYPES = [
  { value: 'all', label: '全部' },
  { value: 'case', label: '接口用例' },
  { value: 'scenario', label: '测试场景' },
  { value: 'suite', label: '测试套件' },
  { value: 'regression', label: '回归测试' },
]

function key(username, projectId) {
  return `wtp_report_type:${encodeURIComponent(username)}:${encodeURIComponent(projectId)}`
}

export function preferredReportType(username, projectId, storage) {
  if (!username || !projectId) return 'all'
  try {
    const value = (storage ?? globalThis.localStorage)?.getItem(key(username, projectId))
    return REPORT_TYPES.some(type => type.value === value) ? value : 'all'
  } catch { return 'all' }
}

export function rememberReportType(username, projectId, value, storage) {
  if (!username || !projectId || !REPORT_TYPES.some(type => type.value === value)) return
  try { (storage ?? globalThis.localStorage)?.setItem(key(username, projectId), value) } catch {}
}
