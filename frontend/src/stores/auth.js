import { defineStore } from 'pinia'
import { ref } from 'vue'
import { listProjects } from '../api/project'

export const useAuthStore = defineStore('auth', () => {
  // 刷新不掉登录:token 持久化到 localStorage
  const token = ref(localStorage.getItem('wtp_token') || '')
  const username = ref(localStorage.getItem('wtp_user') || '')

  // 当前选中的项目:id + name 都存起来,下拉/topbar 显示要用
  const currentProjectId = ref(Number(localStorage.getItem('wtp_pid')) || null)
  const currentProjectName = ref(localStorage.getItem('wtp_pname') || '')

  function setAuth(tk, name) {
    token.value = tk
    username.value = name || ''
    localStorage.setItem('wtp_token', tk)
    localStorage.setItem('wtp_user', username.value)
  }

  function setProject(id, name) {
    currentProjectId.value = id || null
    currentProjectName.value = name || ''
    if (id) {
      localStorage.setItem('wtp_pid', String(id))
      localStorage.setItem('wtp_pname', name || '')
    } else {
      localStorage.removeItem('wtp_pid')
      localStorage.removeItem('wtp_pname')
    }
  }

  // 登录后 / 路由守卫用:确保 currentProjectId 有效
  // 逻辑:拉列表 → 若当前 pid 还在列表里就保留;否则选列表第一个;列表空则清空(触发跳到管理页)
  // 返回 { projects, activeId } 供调用方判断
  async function initProject() {
    try {
      const projects = await listProjects()
      if (!projects.length) {
        setProject(null, '')
        return { projects: [], activeId: null }
      }
      const stillValid = currentProjectId.value && projects.find(p => p.id === currentProjectId.value)
      const active = stillValid || projects[0]
      setProject(active.id, active.name)
      return { projects, activeId: active.id }
    } catch (e) {
      // 拉不到就先算了,不阻塞路由(登录才会触发,401 会被 http 拦截器带回 login)
      return { projects: [], activeId: null }
    }
  }

  function logout() {
    token.value = ''
    username.value = ''
    setProject(null, '')
    localStorage.removeItem('wtp_token')
    localStorage.removeItem('wtp_user')
  }

  return { token, username, currentProjectId, currentProjectName, setAuth, setProject, initProject, logout }
})
