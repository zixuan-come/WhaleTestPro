import http from './http'

export const listRecords = (params = {}) => http.get('/traffic/records', { params: typeof params === 'number' ? { limit: params } : params })
export const getRecord = (id) => http.get(`/traffic/records/${id}`)
export const replayRecord = (id, body) => http.post(`/traffic/replay/${id}`, body || {}, { timeout: 60000 })
export const captureState = () => http.get('/traffic/capture')
export const startCapture = () => http.post('/traffic/capture/start')
export const stopCapture = () => http.post('/traffic/capture/stop')
