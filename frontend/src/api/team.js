import http from './http'

export const listTeams = () => http.get('/teams')
export const createTeam = (data) => http.post('/teams', data)
export const listTeamMembers = (id) => http.get(`/teams/${id}/members`)
export const searchTeamMemberCandidates = (id, params) => http.get(`/teams/${id}/member-candidates`, { params })
export const addTeamMember = (id, data) => http.post(`/teams/${id}/members`, data)
export const updateTeamMemberRole = (teamId, memberId, data) => http.patch(`/teams/${teamId}/members/${memberId}`, data)
export const removeTeamMember = (teamId, memberId) => http.delete(`/teams/${teamId}/members/${memberId}`)
