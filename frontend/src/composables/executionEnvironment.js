import { computed, onScopeDispose, ref, watch } from 'vue'
import { useAuthStore } from '../stores/auth'
import { listEnvironments } from '../api/environment'

// 四个执行页面共用用户/项目偏好，页面自身不再维护独立的环境选择副本。
export function useExecutionEnvironment() {
  const auth = useAuthStore()
  const envs = ref([])
  let requestVersion = 0

  const selectedEnv = computed({
    get() {
      const saved = auth.getPreferredEnv(auth.currentProjectId)
      return envs.value.some(environment => String(environment.id) === saved) ? saved : ''
    },
    set(value) {
      if (value == null || value === '') auth.setPreferredEnv(auth.currentProjectId, '')
      else if (envs.value.some(environment => String(environment.id) === String(value))) {
        auth.setPreferredEnv(auth.currentProjectId, value)
      }
    },
  })

  watch(() => [auth.token, auth.username, auth.currentProjectId], () => {
    requestVersion += 1
    envs.value = []
  }, { flush: 'sync' })
  onScopeDispose(() => { requestVersion += 1 })

  async function loadEnvironments() {
    const version = ++requestVersion
    const sessionToken = auth.token
    const projectId = auth.currentProjectId
    if (!sessionToken || !projectId) return []
    const rows = await listEnvironments()
    if (version !== requestVersion || sessionToken !== auth.token || projectId !== auth.currentProjectId) return []
    if (!Array.isArray(rows)) throw new Error('环境列表格式错误')
    envs.value = rows
    const saved = auth.getPreferredEnv(projectId)
    // 仅成功获取列表后确认失效；请求失败或页面切换不能清除已保存的选择。
    if (saved && !rows.some(environment => String(environment.id) === saved)) auth.setPreferredEnv(projectId, '')
    return rows
  }

  return { envs, selectedEnv, loadEnvironments }
}
