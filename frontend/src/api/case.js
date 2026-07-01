import http from './http'

export const listCases = () => http.get('/cases')
export const getCase = (id) => http.get(`/cases/${id}`)
export const createCase = (data) => http.post('/cases', data)
export const deleteCase = (id) => http.delete(`/cases/${id}`)
// 跑单个用例:env_id 可选;后端同步执行并返回结果 dict(或数据驱动时的数组)
export const runCase = (id, envId) => http.post(`/cases/${id}/run`, null, { params: envId ? { env_id: envId } : {} })
// 跑用例链(场景编排):body 直接是有序的 case_id 数组,变量按 extract_rules 顺序透传
export const runChain = (caseIds, envId) => http.post('/cases/chain', caseIds, { params: envId ? { env_id: envId } : {} })
