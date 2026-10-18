import http from './http'

export const listPerfTasks = () => http.get('/perf/tasks')
export const getPerfTask = (id) => http.get(`/perf/tasks/${id}`)
export const createPerfTask = (data) => http.post('/perf/tasks', data)
export const deletePerfTask = (id) => http.delete(`/perf/tasks/${id}`)
export const runPerfTask = (id) => http.post(`/perf/tasks/${id}/run`)
export const stopPerfTask = (id, executionId) => http.post(`/perf/tasks/${id}/stop`, null, { params: { execution_id: executionId } })
export const updatePerfTask = (id, data) => http.put(`/perf/tasks/${id}`, data)
export const listPerfRuns = (id, params) => http.get(`/perf/tasks/${id}/runs`, { params })
export const getPerfRun = (id, runId) => http.get(`/perf/tasks/${id}/runs/${runId}`)
export const clearPerfRuns = (id, data) => http.post(`/perf/tasks/${id}/runs/clear`, data)
