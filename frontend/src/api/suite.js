import http from './http'

export const listSuites = () => http.get('/suites')
export const createSuite = (data) => http.post('/suites', data)
export const updateSuite = (id, data) => http.put(`/suites/${id}`, data)
export const deleteSuite = (id) => http.delete(`/suites/${id}`)
export const runSuite = (id, envId) =>
  http.post(`/suites/${id}/run`, null, { params: envId ? { env_id: envId } : {} })
