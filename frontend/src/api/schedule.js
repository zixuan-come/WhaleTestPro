import http from './http'

export const listSchedules = () => http.get('/schedules')
export const getSchedule = (id) => http.get(`/schedules/${id}`)
export const createSchedule = (data) => http.post('/schedules', data)
export const updateSchedule = (id, data) => http.put(`/schedules/${id}`, data)
export const deleteSchedule = (id) => http.delete(`/schedules/${id}`)
