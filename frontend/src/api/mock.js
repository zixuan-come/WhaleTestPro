import http from './http'

export const listMocks = () => http.get('/mocks')
export const getMock = (id) => http.get(`/mocks/${id}`)
export const createMock = (data) => http.post('/mocks', data)
export const updateMock = (id, data) => http.put(`/mocks/${id}`, data)
export const deleteMock = (id) => http.delete(`/mocks/${id}`)
