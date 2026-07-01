import http from './http'

export const listPerfTasks = () => http.get('/perf/tasks')
export const getPerfTask = (id) => http.get(`/perf/tasks/${id}`)
export const createPerfTask = (data) => http.post('/perf/tasks', data)
export const deletePerfTask = (id) => http.delete(`/perf/tasks/${id}`)
export const runPerfTask = (id) => http.post(`/perf/tasks/${id}/run`)
