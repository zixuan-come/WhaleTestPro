import http from './http'

export const listReports = (page = 1, pageSize = 20) =>
  http.get('/reports', { params: { page, page_size: pageSize } })
export const getReport = (id) => http.get(`/reports/${id}`)
export const listScenarioReports = (page = 1, pageSize = 20) =>
  http.get('/reports/scenarios', { params: { page, page_size: pageSize } })
export const getScenarioReport = (id) => http.get(`/reports/scenarios/${id}`)

export const listExecutionReports = (params) => http.get('/reports/executions', { params })
export const getExecutionReport = (id) => http.get(`/reports/executions/${encodeURIComponent(id)}`)
export const listReportFolders = () => http.get('/reports/folders')
export const createReportFolder = (data) => http.post('/reports/folders', data)
export const renameReportFolder = (id, data) => http.put(`/reports/folders/${id}`, data)
export const deleteReportFolder = (id) => http.delete(`/reports/folders/${id}`)
export const moveExecutionReports = (data) => http.post('/reports/executions/move', data)
export const deleteExecutionReports = (data) => http.post('/reports/executions/delete', data)
export const deleteExecutionReport = (id) => http.delete(`/reports/executions/${encodeURIComponent(id)}`)
