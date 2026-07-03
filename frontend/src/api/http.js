import axios from 'axios'
import { useAuthStore } from '../stores/auth'

// 统一走 /api 前缀,由 vite 代理转发到后端(生产换成真实域名即可)
const http = axios.create({ baseURL: '/api', timeout: 15000 })

// 请求拦截器:自动带上 JWT + 当前项目 id
http.interceptors.request.use((config) => {
  const auth = useAuthStore()
  if (auth.token) config.headers.Authorization = `Bearer ${auth.token}`
  // 有选中项目才带 header;没选就不带,业务接口会 422(此时前端应该在项目选择/管理页,不该发业务请求)
  if (auth.currentProjectId) config.headers['X-Project-Id'] = auth.currentProjectId
  return config
})

// 响应拦截器:401 自动登出回登录页;统一抛后端 detail
http.interceptors.response.use(
  (res) => res.data,
  (err) => {
    if (err.response?.status === 401) {
      const auth = useAuthStore()
      auth.logout()
      if (location.hash !== '#/login') location.hash = '#/login'
    }
    const detail = err.response?.data?.detail
    return Promise.reject(new Error(detail || err.message || '请求失败'))
  }
)

export default http
