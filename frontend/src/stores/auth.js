import { defineStore } from 'pinia'
import { ref } from 'vue'
import { listProjects } from '../api/project'
import { listTeams } from '../api/team'

export const useAuthStore = defineStore('auth', () => {
  // 刷新不掉登录:token 持久化到 localStorage
  const token = ref(localStorage.getItem('wtp_token') || '')
  const username = ref(localStorage.getItem('wtp_user') || '')

  // 当前选中的项目:id + name 都存起来,下拉/topbar 显示要用
  const currentProjectId = ref(Number(localStorage.getItem('wtp_pid')) || null)
  const currentProjectName = ref(localStorage.getItem('wtp_pname') || '')
  const currentTeamId = ref(Number(localStorage.getItem('wtp_tid')) || null)
  const currentTeamName = ref(localStorage.getItem('wtp_tname') || '')
  const currentTeamRole = ref(localStorage.getItem('wtp_trole') || '')
  const teamStatus = ref('idle')
  let teamRequestVersion = 0

  function setTeam(id, name, role) {
    currentTeamId.value = id || null; currentTeamName.value = name || ''; currentTeamRole.value = role || ''
    if (id) { localStorage.setItem('wtp_tid', String(id)); localStorage.setItem('wtp_tname', name || ''); localStorage.setItem('wtp_trole', role || '') }
    else { localStorage.removeItem('wtp_tid'); localStorage.removeItem('wtp_tname'); localStorage.removeItem('wtp_trole') }
  }

  async function initTeam() {
    const requestVersion = ++teamRequestVersion
    const sessionToken = token.value
    const isCurrent = () => requestVersion === teamRequestVersion && sessionToken === token.value
    teamStatus.value = 'loading'
    try {
      const teams = await listTeams()
      if (!isCurrent()) return { teams: [], activeId: null }
      const active = teams.find(t => t.id === currentTeamId.value) || teams[0]
      if (!active || active.id !== currentTeamId.value) setProject(null, '')
      setTeam(active?.id, active?.name, active?.role)
      teamStatus.value = 'ready'
      return { teams, activeId: active?.id || null }
    } catch (error) {
      if (!isCurrent()) return { teams: [], activeId: null }
      setTeam(null, '', '')
      setProject(null, '')
      teamStatus.value = 'error'
      throw error
    }
  }

  function clearContext() {
    teamRequestVersion += 1
    teamStatus.value = 'idle'
    setTeam(null, '', '')
    setProject(null, '')
  }

  // 用户名在本项目中唯一且不可改名；按账号 + 项目隔离本浏览器的环境偏好。
  // 旧 wtp_env_by_pid 没有账号归属，不能继承给当前登录用户。
  const environmentPreferenceKey = 'wtp_env_by_user_project'
  function readEnvironmentPreferences() {
    try {
      const value = JSON.parse(localStorage.getItem(environmentPreferenceKey) || '{}')
      return value && typeof value === 'object' && !Array.isArray(value) ? value : {}
    } catch { return {} }
  }
  const preferredEnvByUserProject = ref(readEnvironmentPreferences())

  function environmentPreferenceUser() {
    return token.value && username.value ? username.value.trim().toLowerCase() : ''
  }

  function userEnvironmentPreferences(user) {
    const value = Object.hasOwn(preferredEnvByUserProject.value, user) ? preferredEnvByUserProject.value[user] : null
    return value && typeof value === 'object' && !Array.isArray(value) ? value : {}
  }

  function setPreferredEnv(pid, envId) {
    const user = environmentPreferenceUser()
    if (!user || !Number.isSafeInteger(Number(pid)) || Number(pid) <= 0) return
    const empty = envId == null || envId === ''
    if (!empty && (!Number.isSafeInteger(Number(envId)) || Number(envId) <= 0)) return
    preferredEnvByUserProject.value = {
      ...preferredEnvByUserProject.value,
      [user]: { ...userEnvironmentPreferences(user), [String(Number(pid))]: empty ? '' : String(Number(envId)) },
    }
    try { localStorage.setItem(environmentPreferenceKey, JSON.stringify(preferredEnvByUserProject.value)) }
    catch { /* 存储空间不足时仍保留本次会话选择。 */ }
  }

  function getPreferredEnv(pid) {
    const user = environmentPreferenceUser()
    if (!user || !pid) return ''
    const saved = userEnvironmentPreferences(user)[String(Number(pid))]
    if (typeof saved !== 'string' && typeof saved !== 'number') return ''
    return Number.isSafeInteger(Number(saved)) && Number(saved) > 0 ? String(Number(saved)) : ''
  }

  function setAuth(tk, name) {
    if (tk !== token.value) clearContext()
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
    const sessionToken = token.value
    const teamId = currentTeamId.value
    if (!teamId) {
      setProject(null, '')
      return { projects: [], activeId: null }
    }
    try {
      const projects = await listProjects({ team_id: teamId })
      if (sessionToken !== token.value || teamId !== currentTeamId.value) {
        return { projects: [], activeId: null }
      }
      if (!projects.length) {
        setProject(null, '')
        return { projects: [], activeId: null }
      }
      const stillValid = currentProjectId.value && projects.find(p => p.id === currentProjectId.value)
      const active = stillValid || projects[0]
      setProject(active.id, active.name)
      return { projects, activeId: active.id }
    } catch (e) {
      if (sessionToken === token.value && teamId === currentTeamId.value) setProject(null, '')
      // 拉不到就先算了,不阻塞路由(登录才会触发,401 会被 http 拦截器带回 login)
      return { projects: [], activeId: null }
    }
  }

  function logout() {
    clearContext()
    token.value = ''
    username.value = ''
    localStorage.removeItem('wtp_token')
    localStorage.removeItem('wtp_user')
  }

  return { token, username, currentProjectId, currentProjectName, currentTeamId, currentTeamName, currentTeamRole, teamStatus, setAuth, setProject, setTeam, initProject, initTeam, logout, getPreferredEnv, setPreferredEnv }
})
