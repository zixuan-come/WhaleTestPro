import http from './http'

export const listProjects = () => http.get('/projects')
export const createProject = (data) => http.post('/projects', data)
export const getProject = (id) => http.get(`/projects/${id}`)
export const deleteProject = (id) => http.delete(`/projects/${id}`)
