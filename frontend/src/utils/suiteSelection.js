export function suiteCatalog(scenarios, cases, interfaces) {
  const interfaceMap = new Map(interfaces.map(item => [item.id, item]))
  const caseMap = new Map(cases.map(item => [item.id, item]))
  return {
    scenarios: scenarios.map(item => ({ id: item.id, name: item.name, description: item.description || '', case_ids: item.case_ids || [],
      steps: (item.case_ids || []).map(id => ({ id, name: caseMap.get(id)?.name || '已删除的用例' })) })),
    cases: cases.map(item => ({ id: item.id, name: item.name, interface_id: item.interface_id, interface_name: interfaceMap.get(item.interface_id)?.name || '接口已删除' })),
    interfaces: interfaces.map(item => ({ value:String(item.id), label:item.name })),
  }
}

export function selectedSuiteContent(catalog, value) {
  const scenarios = (value.scenario_ids || []).map(id => catalog.scenarios.find(item => item.id === id) || { id, name:`已失效的场景（${id}）`, missing:true, steps:[], case_ids:[] })
  const included = new Set(scenarios.flatMap(item => item.case_ids))
  const cases = (value.case_ids || []).map(id => ({ ...(catalog.cases.find(item => item.id === id) || { id, name:`已失效的用例（${id}）`, missing:true }), included:included.has(id) }))
  return { scenarios, cases, included }
}

export function filterSuiteContent(catalog, { kind, query = '', interfaceId = '' }) {
  const source = kind === 'scenario' ? catalog.scenarios : catalog.cases, needle = query.trim().toLowerCase()
  return source.filter(item => (!needle || `${item.name} ${item.interface_name || ''} ${item.description || ''}`.toLowerCase().includes(needle)) &&
    (kind !== 'case' || ((!interfaceId || String(item.interface_id) === String(interfaceId)))))
}
