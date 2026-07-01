import axios from 'axios'
import { useAuthStore } from '../stores/auth'

// 统一走 /api 前缀,由 vite 代理转发到后端 8000(生产换成真实域名即可)
const http = axios.create({ baseURL: '/api', timeout: 15000 })

// 请求拦截器:自动带上 JWT
http.interceptors.request.use((config) => {
  const auth = useAuthStore()
  if (auth.token) config.headers.Authorization = `Bearer ${auth.token}`
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
