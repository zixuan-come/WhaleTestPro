import http from './http'

export const listInterfaces = () => http.get('/interfaces')
export const getInterface = (id) => http.get(`/interfaces/${id}`)
export const createInterface = (data) => http.post('/interfaces', data)
export const deleteInterface = (id) => http.delete(`/interfaces/${id}`)
