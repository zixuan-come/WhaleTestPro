import http from './http'

export const listRecords = (limit = 100) => http.get('/traffic/records', { params: { limit } })
export const getRecord = (id) => http.get(`/traffic/records/${id}`)
export const replayRecord = (id, body) => http.post(`/traffic/replay/${id}`, body || {})
