import http from './http'

export const listProjects = (params = {}) => http.get('/projects', { params })
export const createProject = (data) => http.post('/projects', data)
export const getProject = (id) => http.get(`/projects/${id}`)
export const updateProject = (id, data) => http.put(`/projects/${id}`, data)
export const deleteProject = (id) => http.delete(`/projects/${id}`)

export const moveProjectToTeam = (id, team_id) => http.post(`/projects/${id}/move-team`, { team_id })

export const getProjectNotifications = (id) => http.get(`/projects/${id}/notifications`)
export const saveProjectNotifications = (id, data) => http.put(`/projects/${id}/notifications`, data)
export const testProjectNotifications = (id) => http.post(`/projects/${id}/notifications/test`)
