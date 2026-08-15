import http from './http'

export const listReports = (page = 1, pageSize = 20) =>
  http.get('/reports', { params: { page, page_size: pageSize } })
export const getReport = (id) => http.get(`/reports/${id}`)
export const listScenarioReports = (page = 1, pageSize = 20) =>
  http.get('/reports/scenarios', { params: { page, page_size: pageSize } })
export const getScenarioReport = (id) => http.get(`/reports/scenarios/${id}`)
