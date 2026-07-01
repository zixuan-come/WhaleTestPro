import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useAuthStore = defineStore('auth', () => {
  // 刷新不掉登录:token 持久化到 localStorage
  const token = ref(localStorage.getItem('wtp_token') || '')
  const username = ref(localStorage.getItem('wtp_user') || '')

  function setAuth(tk, name) {
    token.value = tk
    username.value = name || ''
    localStorage.setItem('wtp_token', tk)
    localStorage.setItem('wtp_user', username.value)
  }
  function logout() {
    token.value = ''
    username.value = ''
    localStorage.removeItem('wtp_token')
    localStorage.removeItem('wtp_user')
  }
  return { token, username, setAuth, logout }
})
