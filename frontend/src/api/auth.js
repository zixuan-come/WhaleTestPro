import http from './http'

export const login = (username, password) => http.post('/auth/login', { username, password })
export const register = (username, password) => http.post('/auth/register', { username, password })
export const logout = () => http.post('/auth/logout')
