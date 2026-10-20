import http from './http'

export const listScenarios = () => http.get('/scenarios')
export const getScenario = (id) => http.get(`/scenarios/${id}`)
export const createScenario = (data) => http.post('/scenarios', data)
export const updateScenario = (id, data) => http.put(`/scenarios/${id}`, data)
export const deleteScenario = (id) => http.delete(`/scenarios/${id}`)
export const runScenario = (id, envId) =>
  http.post(`/scenarios/${id}/run`, null, { params: envId ? { env_id: envId } : {}, timeout: 600000 })

export const debugScenarioStep = (id, envId, data) =>
  http.post(`/scenarios/${id}/debug`, data, { params: { env_id: envId }, timeout:600000 })
export const validateScenarioExtraction = (id, envId, data) =>
  http.post(`/scenarios/${id}/debug/extract`, data, { params: { env_id: envId } })
