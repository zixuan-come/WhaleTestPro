import http from './http'

export const listProjects = (params = {}) => http.get('/projects', { params })
export const createProject = (data) => http.post('/projects', data)
export const getProject = (id) => http.get(`/projects/${id}`)
export const updateProject = (id, data) => http.put(`/projects/${id}`, data)
export const deleteProject = (id) => http.delete(`/projects/${id}`)
export const listProjectMembers = (id) => http.get(`/projects/${id}/members`)
export const searchProjectMemberCandidates = (id, params) =>
  http.get(`/projects/${id}/member-candidates`, { params })
export const addProjectMember = (id, data) => http.post(`/projects/${id}/members`, data)
export const updateProjectMemberRole = (projectId, memberId, data) =>
  http.patch(`/projects/${projectId}/members/${memberId}`, data)
export const removeProjectMember = (projectId, memberId) =>
  http.delete(`/projects/${projectId}/members/${memberId}`)

export const moveProjectToTeam = (id, team_id) => http.post(`/projects/${id}/move-team`, { team_id })
