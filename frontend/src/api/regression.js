import http from './http'

export const regressionOptions = () => http.get('/regression/options')
export const previewRegression = selection => http.post('/regression/preview', selection)
export const runSelectedRegression = selection => http.post('/regression/run', selection, { timeout: 600000 })
