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

function normalizeHttpError(message, response, payload) {
  const error = new Error(message || '请求失败')
  error.status = response?.status ?? payload?.code
  error.code = payload?.code ?? response?.status
  error.data = payload?.data
  error.response = response
  return error
}

// 响应拦截器:401 自动登出回登录页;统一保留状态码和业务 data
http.interceptors.response.use(
  (res) => {
    const body = res.data
    if (body && typeof body === 'object' && 'code' in body && 'message' in body && 'data' in body) {
      if (body.code !== 0) return Promise.reject(normalizeHttpError(body.message, res, body))
      return body.data
    }
    return body
  },
  (err) => {
    if (err.response?.status === 401) {
      const auth = useAuthStore()
      auth.logout()
      if (location.hash !== '#/login') location.hash = '#/login'
    }
    const payload = err.response?.data || {}
    const detail = payload.detail
    const detailMessage = detail && typeof detail === 'object' ? detail.message : detail
    const message = payload.message || detailMessage || err.message
    const normalized = normalizeHttpError(message, err.response, {
      code: payload.code ?? err.response?.status,
      data: payload.data ?? (detail && typeof detail === 'object' ? detail.data : undefined),
    })
    return Promise.reject(normalized)
  }
)

export default http
