import http from './http'

export const listInterfaces = () => http.get('/interfaces')
export const getInterface = (id) => http.get(`/interfaces/${id}`)
export const createInterface = (data) => http.post('/interfaces', data)
export const updateInterface = (id, data) => http.put(`/interfaces/${id}`, data)
export const deleteInterface = (id) => http.delete(`/interfaces/${id}`)

// 分类批量操作:后端一次 SQL 改所有匹配的接口,快过前端循环 PUT
export const renameCategory = (oldName, newName) =>
  http.patch('/interfaces/categories/rename', { old_name: oldName, new_name: newName })
export const deleteCategory = (name) =>
  http.delete(`/interfaces/categories/${encodeURIComponent(name)}`)
