import http from './http'

export const listReports = (page = 1, pageSize = 20) =>
  http.get('/reports', { params: { page, page_size: pageSize } })
export const getReport = (id) => http.get(`/reports/${id}`)
