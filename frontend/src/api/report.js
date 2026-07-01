import http from './http'

export const listReports = () => http.get('/reports')
export const getReport = (id) => http.get(`/reports/${id}`)
