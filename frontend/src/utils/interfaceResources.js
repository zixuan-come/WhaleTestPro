// Keep matching cases below their interface so search never loses context.
export function interfaceResources(interfaces, cases, keyword = '') {
  const query = keyword.trim().toLocaleLowerCase()
  const byInterface = new Map()
  for (const testCase of cases) {
    const key = String(testCase.interface_id)
    if (!byInterface.has(key)) byInterface.set(key, [])
    byInterface.get(key).push(testCase)
  }
  const groups = new Map()
  for (const item of interfaces) {
    const children = byInterface.get(String(item.id)) || []
    const matches = !query || [item.name, item.url, item.method, item.category].filter(Boolean).join(' ').toLocaleLowerCase().includes(query)
    const visibleCases = matches ? children : children.filter(c => c.name.toLocaleLowerCase().includes(query))
    if (!matches && !visibleCases.length) continue
    const category = item.category?.trim() || '未分类'
    if (!groups.has(category)) groups.set(category, [])
    groups.get(category).push({ ...item, cases: visibleCases, caseCount: children.length })
  }
  return [...groups].sort(([a], [b]) => a === b ? 0 : a === '未分类' ? 1 : b === '未分类' ? -1 : a.localeCompare(b, 'zh-CN'))
    .map(([name, items]) => ({ name, items }))
}
