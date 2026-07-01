import http from './http'

export const listEnvironments = () => http.get('/environments')
export const getEnvironment = (id) => http.get(`/environments/${id}`)
export const createEnvironment = (data) => http.post('/environments', data)
export const updateEnvironment = (id, data) => http.put(`/environments/${id}`, data)
export const deleteEnvironment = (id) => http.delete(`/environments/${id}`)
