<script setup>
import { computed, onMounted, ref } from 'vue'
import { useAuthStore } from '../stores/auth'
import { listTeams, listTeamMembers, searchTeamMemberCandidates, updateTeamMemberRole, removeTeamMember, updateTeam, transferTeamOwnership, leaveTeam, deleteTeam, inviteTeamMember, listTeamInvitations, respondTeamInvitation, listTeamPermissions, setTeamPermission } from '../api/team'
import { useFeedback } from '../composables/feedback'

const auth = useAuthStore()
const { showMessage, confirmAction } = useFeedback()
const teams = ref([])
const members = ref([])
const invitations = ref([])
const permissions = ref({})
const loading = ref(false)
const error = ref('')
const keyword = ref('')
const candidates = ref([])
const selected = ref(null)
const addRole = ref('member')
const adding = ref(false)
const searching = ref(false)
const permissionSaving = ref('')
const transferTargetId = ref(null)
const editName = ref('')
const editDescription = ref('')

const permissionOptions = [
  { key: 'interface.write', label: '接口管理', description: '新增、修改和删除接口与分类' },
  { key: 'case.write', label: '测试用例', description: '新增、修改和删除测试用例' },
  { key: 'environment.write', label: '环境配置', description: '维护环境变量和执行环境' },
  { key: 'mock.write', label: 'Mock 服务', description: '新增、修改和删除 Mock 规则' },
  { key: 'schedule.write', label: '定时任务', description: '维护定时执行计划' },
  { key: 'perf.write', label: '性能任务', description: '维护性能测试任务配置' },
  { key: 'scenario.write', label: '业务场景', description: '新增、修改和删除场景' },
  { key: 'suite.write', label: '测试套件', description: '新增、修改和删除测试套件' },
]

const currentTeam = computed(() => teams.value.find(t => t.id === auth.currentTeamId) || teams.value[0] || null)
const canManage = computed(() => ['owner', 'admin'].includes(auth.currentTeamRole))

function applyPermissionRows(rows = []) {
  const next = Object.fromEntries(permissionOptions.map(option => [option.key, false]))
  for (const row of rows) {
    if (row.role === 'member' && Object.hasOwn(next, row.permission)) next[row.permission] = Boolean(row.enabled)
  }
  permissions.value = next
}

async function loadInvitations() {
  try { invitations.value = await listTeamInvitations() } catch { invitations.value = [] }
}

async function respondInvitation(invite, accept) {
  try {
    await respondTeamInvitation(invite.id, accept)
    await loadInvitations()
    if (accept) await load()
  } catch (e) { showMessage(e.message || '邀请处理失败', 'error') }
}

async function loadTeamDetails(team) {
  if (!team) {
    members.value = []
    applyPermissionRows()
    return
  }
  const [memberRows, permissionRows] = await Promise.all([
    listTeamMembers(team.id),
    listTeamPermissions(team.id),
  ])
  members.value = memberRows
  applyPermissionRows(permissionRows)
  editName.value = team.name
  editDescription.value = team.description || ''
  transferTargetId.value = members.value.find(member => member.role !== 'owner')?.user_id || null
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    teams.value = await listTeams()
    const team = teams.value.find(item => item.id === auth.currentTeamId) || teams.value[0] || null
    if (team) auth.setTeam(team.id, team.name, team.role || '')
    await loadTeamDetails(team)
  } catch (e) { error.value = e.message || '加载失败' } finally { loading.value = false }
}

async function switchTeam(team) {
  auth.setTeam(team.id, team.name, team.role || '')
  auth.setProject(null, '')
  await loadTeamDetails(team)
}

async function search() {
  selected.value = null
  if (!canManage.value || keyword.value.trim().length < 2 || !currentTeam.value) {
    candidates.value = []
    return
  }
  searching.value = true
  try { candidates.value = await searchTeamMemberCandidates(currentTeam.value.id, { keyword: keyword.value.trim(), limit: 20 }) } catch { candidates.value = [] } finally { searching.value = false }
}

async function addMember() {
  if (!selected.value || !currentTeam.value) return
  adding.value = true
  try {
    await inviteTeamMember(currentTeam.value.id, { user_id: selected.value.id, role: addRole.value })
    showMessage('邀请已发送')
    keyword.value = ''
    selected.value = null
    candidates.value = []
    members.value = await listTeamMembers(currentTeam.value.id)
  } catch (e) { showMessage(e.message || '添加失败', 'error') } finally { adding.value = false }
}

async function saveTeamInfo() {
  if (!currentTeam.value || !canManage.value) return
  try {
    const updated = await updateTeam(currentTeam.value.id, { name: editName.value.trim(), description: editDescription.value.trim() || null })
    const index = teams.value.findIndex(team => team.id === updated.id)
    if (index >= 0) teams.value[index] = { ...teams.value[index], ...updated }
    auth.setTeam(updated.id, updated.name, auth.currentTeamRole)
    showMessage('团队信息已更新')
  } catch (e) { showMessage(e.message || '更新失败', 'error') }
}

async function transferOwner() {
  const target = members.value.find(member => member.user_id === Number(transferTargetId.value) && member.role !== 'owner')
  if (!currentTeam.value || !target || !(await confirmAction(`确认将团队所有权转让给“${target.user.username}”吗？`))) return
  try {
    await transferTeamOwnership(currentTeam.value.id, { user_id: target.user_id })
    showMessage('所有权已转让')
    await load()
  } catch (e) { showMessage(e.message || '转让失败', 'error') }
}

async function leaveCurrentTeam() {
  if (!currentTeam.value || auth.currentTeamRole === 'owner' || !(await confirmAction(`确认退出团队“${currentTeam.value.name}”吗？`))) return
  try {
    await leaveTeam(currentTeam.value.id)
    auth.setTeam(null, '', '')
    auth.setProject(null, '')
    showMessage('已退出团队')
    await load()
  } catch (e) { showMessage(e.message || '退出失败', 'error') }
}

async function deleteCurrentTeam() {
  if (!currentTeam.value || auth.currentTeamRole !== 'owner' || !(await confirmAction(`确认删除团队“${currentTeam.value.name}”吗？团队下不能有项目。`))) return
  try {
    await deleteTeam(currentTeam.value.id)
    auth.setTeam(null, '', '')
    auth.setProject(null, '')
    showMessage('团队已删除')
    await load()
  } catch (e) { showMessage(e.message || '删除失败', 'error') }
}

async function changeRole(member, role) {
  if (!currentTeam.value || member.role === role) return
  try {
    const updated = await updateTeamMemberRole(currentTeam.value.id, member.id, { role })
    const index = members.value.findIndex(item => item.id === member.id)
    if (index >= 0) members.value[index] = updated
  } catch (e) { showMessage(e.message || '角色更新失败', 'error') }
}

async function remove(member) {
  if (!currentTeam.value || member.role === 'owner' || !(await confirmAction(`确认移除成员“${member.user.username}”吗？`))) return
  try {
    await removeTeamMember(currentTeam.value.id, member.id)
    members.value = members.value.filter(item => item.id !== member.id)
    showMessage('成员已移除')
  } catch (e) { showMessage(e.message || '移除失败', 'error') }
}

async function togglePermission(option, event) {
  if (!currentTeam.value || !canManage.value) return
  const previous = Boolean(permissions.value[option.key])
  const enabled = event.target.checked
  permissions.value = { ...permissions.value, [option.key]: enabled }
  permissionSaving.value = option.key
  try {
    await setTeamPermission(currentTeam.value.id, { role: 'member', permission: option.key, enabled })
    showMessage(`${option.label}权限已更新`)
  } catch (e) {
    permissions.value = { ...permissions.value, [option.key]: previous }
    showMessage(e.message || '权限更新失败', 'error')
  } finally { permissionSaving.value = '' }
}

onMounted(() => { load(); loadInvitations() })
</script>

<template>
  <div class="team-page">
    <div class="page-head">
      <div><h2>团队管理</h2><p>管理团队、成员及普通成员的模块写权限。</p></div>
      <div v-if="currentTeam" class="team-actions">
        <button v-if="auth.currentTeamRole !== 'owner'" class="btn btn-ghost" @click="leaveCurrentTeam">退出团队</button>
        <button v-if="auth.currentTeamRole === 'owner'" class="btn btn-ghost danger" @click="deleteCurrentTeam">删除团队</button>
      </div>
    </div>
    <div v-if="invitations.some(invite => invite.status === 'pending')" class="invite-panel">
      <div class="panel-head">待处理邀请</div>
      <div v-for="invite in invitations.filter(item => item.status === 'pending')" :key="invite.id" class="invite-row">
        <span>{{ `团队 #${invite.team_id}` }} · {{ invite.role === 'admin' ? '管理员' : '成员' }}</span>
        <span><button class="btn btn-ghost" @click="respondInvitation(invite, false)">拒绝</button><button class="btn btn-primary" @click="respondInvitation(invite, true)">接受</button></span>
      </div>
    </div>
    <div v-if="loading" class="state">加载中…</div>
    <div v-else-if="error" class="state err">{{ error }} <button class="btn btn-ghost" @click="load">重试</button></div>
    <div v-else class="team-grid">
      <section class="panel team-list">
        <div class="panel-head">我的团队 <span class="count">{{ teams.length }}</span></div>
        <button v-for="team in teams" :key="team.id" class="team-item" :class="{ active: currentTeam && team.id === currentTeam.id }" @click="switchTeam(team)"><span>{{ team.name }}</span><small>{{ team.id === auth.currentTeamId ? '当前团队' : '切换' }}</small></button>
        <div v-if="!teams.length" class="state">还没有团队，请从顶部创建。</div>
      </section>
      <div class="team-main">
        <section class="panel member-panel">
          <div v-if="currentTeam && canManage" class="team-edit">
            <input v-model="editName" :placeholder="currentTeam.name" />
            <input v-model="editDescription" placeholder="团队简介" />
            <button class="btn btn-ghost" @click="saveTeamInfo">保存</button>
            <template v-if="auth.currentTeamRole === 'owner'">
              <select v-model="transferTargetId" class="transfer-select"><option :value="null">选择新所有者</option><option v-for="member in members.filter(item => item.role !== 'owner')" :key="member.id" :value="member.user_id">{{ member.user.username }}</option></select>
              <button class="btn btn-ghost" :disabled="!transferTargetId" @click="transferOwner">转让所有权</button>
            </template>
          </div>
          <div class="panel-head"><span>{{ currentTeam ? currentTeam.name : '团队成员' }} · 成员</span><span class="count">{{ members.length }} 位</span></div>
          <div v-if="!currentTeam" class="state">请选择一个团队。</div>
          <template v-else>
            <div v-if="canManage" class="add-bar">
              <input v-model="keyword" placeholder="搜索用户名（至少 2 个字符）" @input="search" />
              <select v-model="addRole"><option value="member">成员</option><option value="admin">管理员</option></select>
              <button class="btn btn-primary" :disabled="!selected || adding" @click="addMember">添加</button>
              <div v-if="candidates.length" class="candidate-list"><button v-for="candidate in candidates" :key="candidate.id" @click="selected = candidate; keyword = candidate.username; candidates = []">{{ candidate.username }}</button></div>
            </div>
            <div v-else class="permission-tip">你是团队成员，只能查看团队成员和权限配置。</div>
            <div class="member-table">
              <div v-for="member in members" :key="member.id" class="member-row">
                <div><strong>{{ member.user.username }}</strong><small>#{{ member.user_id }}</small></div>
                <select :value="member.role" :disabled="!canManage || member.role === 'owner'" @change="changeRole(member, $event.target.value)"><option value="owner">所有者</option><option value="admin">管理员</option><option value="member">成员</option></select>
                <button class="icon-btn" :disabled="!canManage || member.role === 'owner'" @click="remove(member)">删除</button>
              </div>
              <div v-if="!members.length" class="state">当前团队还没有成员。</div>
            </div>
          </template>
        </section>
        <section v-if="currentTeam" class="panel permission-panel">
          <div class="panel-head"><span>普通成员写权限</span><span class="count">Owner / Admin 默认拥有全部权限</span></div>
          <p class="permission-description">读取和执行权限默认开放给团队成员；下面仅控制普通成员能否修改对应模块。</p>
          <div class="permission-grid">
            <label v-for="option in permissionOptions" :key="option.key" class="permission-card" :class="{ disabled: !canManage }">
              <span><strong>{{ option.label }}</strong><small>{{ option.description }}</small></span>
              <input type="checkbox" :checked="permissions[option.key]" :disabled="!canManage || permissionSaving === option.key" @change="togglePermission(option, $event)" />
            </label>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>

<style scoped>
.team-page { max-width:1100px; margin:0 auto; }
.page-head { display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:22px; }
.page-head h2 { font-size:20px; margin:0 0 6px; }
.page-head p { margin:0; color:var(--text-muted); font-size:13px; }
.team-grid { display:grid; grid-template-columns:280px minmax(0,1fr); gap:18px; align-items:start; }
.team-main { display:grid; gap:18px; min-width:0; }
.panel { background:var(--surface); border:1px solid var(--border); border-radius:14px; overflow:hidden; }
.panel-head { display:flex; justify-content:space-between; align-items:center; padding:15px 18px; border-bottom:1px solid var(--border); font-weight:700; font-size:13px; }
.count { color:var(--text-muted); font-size:11px; font-weight:500; }
.team-item { width:100%; display:flex; justify-content:space-between; padding:13px 18px; border:0; border-bottom:1px solid var(--border); background:none; color:var(--text); text-align:left; cursor:pointer; font:inherit; }
.team-item:hover, .team-item.active { background:var(--surface-2); color:var(--primary); }
.team-item small { color:var(--text-muted); font-size:11px; }
.add-bar { position:relative; display:grid; grid-template-columns:minmax(0,1fr) 110px 64px; gap:8px; padding:14px 18px; border-bottom:1px solid var(--border); }
.add-bar input, .add-bar select, .member-row select { height:34px; border:1px solid var(--border); border-radius:7px; background:var(--surface-2); color:var(--text); padding:0 9px; font:inherit; font-size:12px; }
.candidate-list { position:absolute; left:18px; right:18px; top:53px; z-index:2; padding:4px; background:var(--surface); border:1px solid var(--border); border-radius:8px; box-shadow:var(--shadow-md); }
.candidate-list button { display:block; width:100%; padding:8px 10px; border:0; background:none; text-align:left; color:var(--text); cursor:pointer; }
.candidate-list button:hover { background:var(--surface-2); }
.permission-tip { padding:12px 18px; color:var(--text-muted); font-size:12px; background:var(--surface-2); }
.member-row { display:grid; grid-template-columns:minmax(0,1fr) 115px 44px; gap:12px; align-items:center; padding:12px 18px; border-bottom:1px solid var(--border); font-size:13px; }
.member-row small { display:block; color:var(--text-muted); font-size:11px; margin-top:3px; }
.icon-btn { border:0; background:none; color:var(--fail-fg); cursor:pointer; font-size:12px; }
.icon-btn:disabled { opacity:.35; cursor:not-allowed; }
.state { padding:34px 18px; text-align:center; color:var(--text-muted); font-size:12px; }
.err { color:var(--fail-fg); }
.team-edit { display:flex; gap:8px; padding:12px 18px; border-bottom:1px solid var(--border); }
.team-edit input { flex:1; min-width:0; height:32px; border:1px solid var(--border); border-radius:6px; padding:0 8px; background:var(--surface-2); color:var(--text); }
.transfer-select { height:32px; border:1px solid var(--border); border-radius:6px; padding:0 8px; background:var(--surface-2); color:var(--text); font:inherit; font-size:12px; }
.danger { color:var(--fail-fg); }
.permission-description { margin:0; padding:14px 18px 4px; color:var(--text-muted); font-size:12px; line-height:1.6; }
.permission-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px; padding:14px 18px 18px; }
.permission-card { display:flex; align-items:center; justify-content:space-between; gap:14px; padding:13px; border:1px solid var(--border); border-radius:10px; background:var(--surface-2); cursor:pointer; }
.permission-card.disabled { cursor:default; opacity:.72; }
.permission-card strong { display:block; font-size:13px; }
.permission-card small { display:block; margin-top:4px; color:var(--text-muted); font-size:11px; line-height:1.45; }
.permission-card input { width:16px; height:16px; accent-color:var(--primary); }
@media (max-width:800px) { .team-grid { grid-template-columns:1fr; } .team-edit { flex-wrap:wrap; } .permission-grid { grid-template-columns:1fr; } }
</style>
