<script setup>
import { computed, onMounted, ref } from 'vue'
import { useAuthStore } from '../stores/auth'
import { listTeams, listTeamMembers, searchTeamMemberCandidates, addTeamMember, updateTeamMemberRole, removeTeamMember, updateTeam, transferTeamOwnership, leaveTeam, deleteTeam, inviteTeamMember, listTeamInvitations, respondTeamInvitation } from '../api/team'
import { useFeedback } from '../composables/feedback'

const auth = useAuthStore()
const { showMessage, confirmAction } = useFeedback()
const teams = ref([])
const members = ref([])
const invitations = ref([])
const loading = ref(false)
const error = ref('')
const keyword = ref('')
const candidates = ref([])
const selected = ref(null)
const addRole = ref('member')
const adding = ref(false)
const searching = ref(false)
const transferTargetId = ref(null)
const editName = ref('')
const editDescription = ref('')

const currentTeam = computed(() => teams.value.find(t => t.id === auth.currentTeamId) || teams.value[0] || null)
const canManage = computed(() => ['owner', 'admin'].includes(auth.currentTeamRole))

async function loadInvitations() { try { invitations.value = await listTeamInvitations() } catch { invitations.value = [] } }
async function respondInvitation(invite, accept) { try { await respondTeamInvitation(invite.id, accept); await loadInvitations(); if (accept) await load() } catch (e) { showMessage(e.message || "邀请处理失败", "error") } }
async function load() {
  loading.value = true; error.value = ''
  try {
    teams.value = await listTeams()
    if (!auth.currentTeamId && teams.value[0]) auth.setTeam(teams.value[0].id, teams.value[0].name, teams.value[0].role || '')
    if (currentTeam.value) {
      editName.value = currentTeam.value.name
      editDescription.value = currentTeam.value.description || ''
      members.value = await listTeamMembers(currentTeam.value.id)
      transferTargetId.value = members.value.find(m => m.role !== 'owner')?.user_id || null
    }
  } catch (e) { error.value = e.message || '加载失败' } finally { loading.value = false }
}
async function switchTeam(team) {
  auth.setTeam(team.id, team.name, team.role || '')
  auth.setProject(null, '')
  members.value = await listTeamMembers(team.id)
  editName.value = team.name
  editDescription.value = team.description || ''
  transferTargetId.value = members.value.find(m => m.role !== 'owner')?.user_id || null
}
async function search() {
  selected.value = null
  if (!canManage.value || keyword.value.trim().length < 2 || !currentTeam.value) { candidates.value = []; return }
  searching.value = true
  try { candidates.value = await searchTeamMemberCandidates(currentTeam.value.id, { keyword: keyword.value.trim(), limit: 20 }) } catch (e) { candidates.value = [] } finally { searching.value = false }
}
async function addMember() {
  if (!selected.value || !currentTeam.value) return
  adding.value = true
  try { await inviteTeamMember(currentTeam.value.id, { user_id: selected.value.id, role: addRole.value }); showMessage('邀请已发送'); keyword.value = ''; selected.value = null; candidates.value = []; members.value = await listTeamMembers(currentTeam.value.id) } catch (e) { showMessage(e.message || '添加失败', 'error') } finally { adding.value = false }
}
async function saveTeamInfo() {
  if (!currentTeam.value || !canManage.value) return
  try { const updated = await updateTeam(currentTeam.value.id, { name: editName.value.trim(), description: editDescription.value.trim() || null }); const i = teams.value.findIndex(t => t.id === updated.id); if (i >= 0) teams.value[i] = { ...teams.value[i], ...updated }; auth.setTeam(updated.id, updated.name, auth.currentTeamRole); showMessage('团队信息已更新') } catch (e) { showMessage(e.message || '更新失败', 'error') }
}
async function transferOwner() {
  const target = members.value.find(m => m.user_id === Number(transferTargetId.value) && m.role !== 'owner')
  if (!currentTeam.value || !target || !(await confirmAction(`确认将团队所有权转让给“${target.user.username}”吗？`))) return
  try { await transferTeamOwnership(currentTeam.value.id, { user_id: target.user_id }); showMessage('所有权已转让'); await load() } catch (e) { showMessage(e.message || '转让失败', 'error') }
}
async function leaveCurrentTeam() {
  if (!currentTeam.value || auth.currentTeamRole === 'owner' || !(await confirmAction(`确认退出团队“${currentTeam.value.name}”吗？`))) return
  try { await leaveTeam(currentTeam.value.id); auth.setTeam(null, '', ''); auth.setProject(null, ''); showMessage('已退出团队'); await load() } catch (e) { showMessage(e.message || '退出失败', 'error') }
}
async function deleteCurrentTeam() {
  if (!currentTeam.value || auth.currentTeamRole !== 'owner' || !(await confirmAction(`确认删除团队“${currentTeam.value.name}”吗？团队下不能有项目。`))) return
  try { await deleteTeam(currentTeam.value.id); auth.setTeam(null, '', ''); auth.setProject(null, ''); showMessage('团队已删除'); await load() } catch (e) { showMessage(e.message || '删除失败', 'error') }
}
async function changeRole(member, role) {
  if (!currentTeam.value || member.role === role) return
  try { const updated = await updateTeamMemberRole(currentTeam.value.id, member.id, { role }); const i = members.value.findIndex(m => m.id === member.id); if (i >= 0) members.value[i] = updated } catch (e) { showMessage(e.message || '角色更新失败', 'error') }
}
async function remove(member) {
  if (!currentTeam.value || member.role === 'owner' || !(await confirmAction(`确认移除成员“${member.user.username}”吗？`))) return
  try { await removeTeamMember(currentTeam.value.id, member.id); members.value = members.value.filter(m => m.id !== member.id); showMessage('成员已移除') } catch (e) { showMessage(e.message || '移除失败', 'error') }
}
onMounted(() => { load(); loadInvitations() })
</script>

<template>
  <div class="team-page">
    <div class="page-head"><div><h2>团队管理</h2><p>管理团队、成员及成员身份权限。</p></div><div v-if="currentTeam" class="team-actions"><button v-if="auth.currentTeamRole !== 'owner'" class="btn btn-ghost" @click="leaveCurrentTeam">退出团队</button><button v-if="auth.currentTeamRole === 'owner'" class="btn btn-ghost danger" @click="deleteCurrentTeam">删除团队</button></div></div>
    <div v-if="invitations.some(i => i.status === 'pending')" class="invite-panel"><div class="panel-head">待处理邀请</div><div v-for="invite in invitations.filter(i => i.status === 'pending')" :key="invite.id" class="invite-row"><span>{{ `团队 #${invite.team_id}` }} · {{ invite.role === 'admin' ? '管理员' : '成员' }}</span><span><button class="btn btn-ghost" @click="respondInvitation(invite, false)">拒绝</button><button class="btn btn-primary" @click="respondInvitation(invite, true)">接受</button></span></div></div>
    <div v-if="loading" class="state">加载中…</div>
    <div v-else-if="error" class="state err">{{ error }} <button class="btn btn-ghost" @click="load">重试</button></div>
    <div v-else class="team-grid">
      <section class="panel team-list"><div class="panel-head">我的团队 <span class="count">{{ teams.length }}</span></div><button v-for="team in teams" :key="team.id" class="team-item" :class="{ active: currentTeam && team.id === currentTeam.id }" @click="switchTeam(team)"><span>{{ team.name }}</span><small>{{ team.id === auth.currentTeamId ? '当前团队' : '切换' }}</small></button><div v-if="!teams.length" class="state">还没有团队，请从顶部创建。</div></section>
      <section class="panel member-panel"><div v-if="currentTeam && canManage" class="team-edit"><input v-model="editName" :placeholder="currentTeam.name" /><input v-model="editDescription" placeholder="团队简介" /><button class="btn btn-ghost" @click="saveTeamInfo">保存</button><template v-if="auth.currentTeamRole === 'owner'"><select v-model="transferTargetId" class="transfer-select"><option :value="null">选择新所有者</option><option v-for="member in members.filter(m => m.role !== 'owner')" :key="member.id" :value="member.user_id">{{ member.user.username }}</option></select><button class="btn btn-ghost" :disabled="!transferTargetId" @click="transferOwner">转让所有权</button></template></div><div class="panel-head"><span>{{ currentTeam ? currentTeam.name : '团队成员' }} · 成员</span><span class="count">{{ members.length }} 位</span></div><div v-if="!currentTeam" class="state">请选择一个团队。</div><template v-else><div v-if="canManage" class="add-bar"><input v-model="keyword" placeholder="搜索用户名（至少 2 个字符）" @input="search" /><select v-model="addRole"><option value="member">成员</option><option value="admin">管理员</option></select><button class="btn btn-primary" :disabled="!selected || adding" @click="addMember">添加</button><div v-if="candidates.length" class="candidate-list"><button v-for="c in candidates" :key="c.id" @click="selected = c; keyword = c.username; candidates = []">{{ c.username }}</button></div></div><div v-else class="permission-tip">你是团队成员，只能查看团队成员，不能修改成员身份。</div><div class="member-table"><div v-for="member in members" :key="member.id" class="member-row"><div><strong>{{ member.user.username }}</strong><small>#{{ member.user_id }}</small></div><select :value="member.role" :disabled="!canManage || member.role === 'owner'" @change="changeRole(member, $event.target.value)"><option value="owner">所有者</option><option value="admin">管理员</option><option value="member">成员</option></select><button class="icon-btn" :disabled="!canManage || member.role === 'owner'" @click="remove(member)">删除</button></div><div v-if="!members.length" class="state">当前团队还没有成员。</div></div></template></section>
    </div>
  </div>
</template><style scoped>
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
.team-edit { display:flex; gap:8px; padding:12px 18px; border-bottom:1px solid var(--border); } .team-edit input { flex:1; min-width:0; height:32px; border:1px solid var(--border); border-radius:6px; padding:0 8px; background:var(--surface-2); color:var(--text); } .transfer-select { height:32px; border:1px solid var(--border); border-radius:6px; padding:0 8px; background:var(--surface-2); color:var(--text); font:inherit; font-size:12px; } .danger { color:var(--fail-fg); } @media (max-width:800px) { .team-grid { grid-template-columns:1fr; } .team-edit { flex-wrap:wrap; } }
</style>
