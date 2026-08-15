<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import Modal from './Modal.vue'
import {
  addProjectMember,
  listProjectMembers,
  removeProjectMember,
  searchProjectMemberCandidates,
  updateProjectMemberRole,
} from '../api/project'

const props = defineProps({
  project: { type: Object, required: true },
})
const emit = defineEmits(['close'])

const members = ref([])
const loading = ref(true)
const error = ref('')
const candidateKeyword = ref('')
const candidates = ref([])
const candidateLoading = ref(false)
const candidateError = ref('')
const selectedCandidate = ref(null)
const addRole = ref('member')
const adding = ref(false)
const addError = ref('')
const savingMemberId = ref(null)
const removingMemberId = ref(null)
let searchTimer = null

const busy = computed(() => adding.value || savingMemberId.value !== null || removingMemberId.value !== null)

async function loadMembers() {
  loading.value = true
  error.value = ''
  try {
    members.value = await listProjectMembers(props.project.id)
  } catch (err) {
    error.value = err.message || '成员列表加载失败'
  } finally {
    loading.value = false
  }
}

function resetCandidateForm() {
  candidateKeyword.value = ''
  candidates.value = []
  candidateError.value = ''
  selectedCandidate.value = null
  addRole.value = 'member'
  addError.value = ''
}

function onCandidateInput() {
  selectedCandidate.value = null
  candidates.value = []
  candidateError.value = ''
  if (searchTimer) clearTimeout(searchTimer)

  const keyword = candidateKeyword.value.trim()
  if (keyword.length < 2) return

  searchTimer = setTimeout(async () => {
    candidateLoading.value = true
    try {
      candidates.value = await searchProjectMemberCandidates(props.project.id, {
        keyword,
        limit: 20,
      })
    } catch (err) {
      candidateError.value = err.message || '用户搜索失败'
    } finally {
      candidateLoading.value = false
    }
  }, 260)
}

function selectCandidate(candidate) {
  selectedCandidate.value = candidate
  candidateKeyword.value = candidate.username
  candidates.value = []
  candidateError.value = ''
}

async function submitMember() {
  addError.value = ''
  if (!selectedCandidate.value) {
    addError.value = '请先搜索并选择一个用户'
    return
  }

  adding.value = true
  try {
    await addProjectMember(props.project.id, {
      user_id: selectedCandidate.value.id,
      role: addRole.value,
    })
    resetCandidateForm()
    await loadMembers()
  } catch (err) {
    addError.value = err.message || '添加成员失败'
  } finally {
    adding.value = false
  }
}

async function changeRole(member, role) {
  if (member.role === role) return
  addError.value = ''
  savingMemberId.value = member.id
  try {
    const updated = await updateProjectMemberRole(props.project.id, member.id, { role })
    const index = members.value.findIndex((item) => item.id === member.id)
    if (index !== -1) members.value[index] = updated
  } catch (err) {
    error.value = err.message || '角色更新失败'
    await loadMembers()
  } finally {
    savingMemberId.value = null
  }
}

async function removeMember(member) {
  if (!confirm(`确认移除成员“${member.user.username}”吗？`)) return

  error.value = ''
  removingMemberId.value = member.id
  try {
    await removeProjectMember(props.project.id, member.id)
    members.value = members.value.filter((item) => item.id !== member.id)
  } catch (err) {
    error.value = err.message || '移除成员失败'
  } finally {
    removingMemberId.value = null
  }
}

watch(
  () => props.project.id,
  () => {
    resetCandidateForm()
    loadMembers()
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  if (searchTimer) clearTimeout(searchTimer)
})
</script>

<template>
  <Modal :title="`成员管理 · ${project.name}`" :max-width="760" :busy="busy" @close="emit('close')">
    <div class="member-toolbar">
      <div>
        <div class="section-title">添加成员</div>
        <div class="section-note">搜索用户名后选择用户，再设置项目角色。</div>
      </div>
      <span class="member-count">{{ members.length }} 位成员</span>
    </div>

    <div class="add-row">
      <div class="search-wrap">
        <input
          v-model="candidateKeyword"
          type="search"
          placeholder="输入至少 2 个字符搜索用户名"
          @input="onCandidateInput"
        />
        <span v-if="candidateLoading" class="search-state">搜索中…</span>
        <div v-if="candidates.length" class="candidate-menu">
          <button
            v-for="candidate in candidates"
            :key="candidate.id"
            type="button"
            class="candidate-item"
            @click="selectCandidate(candidate)"
          >
            <span class="candidate-avatar">{{ candidate.username.slice(0, 1).toUpperCase() }}</span>
            <span>{{ candidate.username }}</span>
          </button>
        </div>
      </div>
      <select v-model="addRole" aria-label="新成员角色">
        <option value="member">成员</option>
        <option value="admin">管理员</option>
      </select>
      <button class="btn btn-primary" :disabled="adding || !selectedCandidate" @click="submitMember">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14" /></svg>
        {{ adding ? '添加中…' : '添加' }}
      </button>
    </div>

    <div v-if="selectedCandidate" class="selected-user">
      已选择 <strong>{{ selectedCandidate.username }}</strong>
      <button type="button" title="取消选择" @click="resetCandidateForm">取消</button>
    </div>
    <div v-if="candidateError || addError" class="inline-error">{{ candidateError || addError }}</div>

    <div class="member-divider"></div>
    <div class="section-title member-list-title">当前成员</div>

    <div v-if="loading" class="state">加载中…</div>
    <div v-else-if="error" class="state error-state">
      {{ error }}
      <button class="btn btn-ghost" @click="loadMembers">重试</button>
    </div>
    <div v-else-if="!members.length" class="state">当前项目还没有成员。</div>
    <div v-else class="member-list">
      <div v-for="member in members" :key="member.id" class="member-row">
        <span class="member-avatar">{{ member.user.username.slice(0, 1).toUpperCase() }}</span>
        <div class="member-info">
          <strong>{{ member.user.username }}</strong>
          <small>#{{ member.user_id }} · {{ new Date(member.created_at).toLocaleString('zh-CN', { hour12: false }) }}</small>
        </div>
        <select
          :value="member.role"
          :disabled="member.role === 'owner' || savingMemberId === member.id"
          :aria-label="`${member.user.username} 的角色`"
          @change="changeRole(member, $event.target.value)"
        >
          <option value="owner">所有者</option>
          <option value="admin">管理员</option>
          <option value="member">成员</option>
        </select>
        <button
          class="icon-btn danger"
          type="button"
          title="移除成员"
          :disabled="member.role === 'owner' || removingMemberId === member.id"
          @click="removeMember(member)"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14" /></svg>
        </button>
      </div>
    </div>
  </Modal>
</template>

<style scoped>
.member-toolbar { display:flex; align-items:flex-start; justify-content:space-between; gap:16px; margin-bottom:14px; }
.section-title { color:var(--text); font-size:13px; font-weight:700; }
.section-note { margin-top:5px; color:var(--text-muted); font-size:12px; }
.member-count { flex-shrink:0; padding:4px 10px; border-radius:99px; background:var(--surface-2); color:var(--text-muted); font-size:11px; font-weight:600; }

.add-row { display:grid; grid-template-columns:minmax(0,1fr) 112px auto; gap:8px; align-items:start; }
.search-wrap { position:relative; }
.search-wrap input, .add-row select, .member-row select { height:34px; width:100%; padding:0 10px; color:var(--text); background:var(--surface-2); border:1px solid var(--border); border-radius:6px; font:inherit; font-size:12px; }
.search-wrap input:focus, .add-row select:focus, .member-row select:focus { outline:none; border-color:var(--primary); }
.search-state { position:absolute; right:10px; top:9px; color:var(--text-muted); font-size:11px; }
.candidate-menu { position:absolute; z-index:4; top:40px; left:0; right:0; max-height:180px; overflow:auto; padding:4px; background:var(--surface); border:1px solid var(--border); border-radius:8px; box-shadow:var(--shadow-md); }
.candidate-item { display:flex; align-items:center; gap:9px; width:100%; padding:8px; border:0; border-radius:5px; color:var(--text); background:none; text-align:left; cursor:pointer; font:inherit; font-size:12px; }
.candidate-item:hover { background:var(--surface-2); color:var(--primary); }
.candidate-avatar, .member-avatar { display:inline-grid; place-items:center; flex-shrink:0; width:28px; height:28px; border-radius:50%; background:var(--ring); color:var(--primary); font-size:11px; font-weight:700; }
.selected-user { display:flex; align-items:center; gap:5px; margin-top:9px; color:var(--text-muted); font-size:12px; }
.selected-user strong { color:var(--text); }
.selected-user button { padding:0; border:0; background:none; color:var(--primary); cursor:pointer; font:inherit; font-size:12px; }
.inline-error { margin-top:10px; padding:8px 10px; border-radius:6px; background:var(--fail-bg); color:var(--fail-fg); font-size:12px; }
.member-divider { height:1px; margin:20px 0 16px; background:var(--border); }
.member-list-title { margin-bottom:10px; }
.member-list { border:1px solid var(--border); border-radius:8px; overflow:hidden; }
.member-row { display:grid; grid-template-columns:28px minmax(0,1fr) 112px 32px; align-items:center; gap:10px; min-height:58px; padding:9px 12px; border-bottom:1px solid var(--border); }
.member-row:last-child { border-bottom:0; }
.member-row:hover { background:var(--surface-2); }
.member-info { min-width:0; display:flex; flex-direction:column; gap:4px; }
.member-info strong { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:12.5px; }
.member-info small { color:var(--text-muted); font-size:10.5px; }
.member-row select:disabled { opacity:.7; cursor:not-allowed; }
.icon-btn { display:inline-flex; align-items:center; justify-content:center; width:30px; height:30px; padding:0; border:0; border-radius:5px; color:var(--text-muted); background:none; cursor:pointer; }
.icon-btn svg { width:15px; height:15px; }
.icon-btn:hover:not(:disabled) { color:var(--fail-fg); background:var(--fail-bg); }
.icon-btn:disabled { opacity:.35; cursor:not-allowed; }
.state { padding:28px 12px; text-align:center; color:var(--text-muted); font-size:12px; }
.error-state { color:var(--fail-fg); }
.error-state .btn { margin-left:8px; }

@media (max-width:600px) {
  .add-row { grid-template-columns:1fr 100px; }
  .add-row .btn { grid-column:1 / -1; }
  .member-row { grid-template-columns:28px minmax(0,1fr) 32px; }
  .member-row select { grid-column:2; grid-row:2; width:112px; }
  .member-row .icon-btn { grid-column:3; grid-row:1 / span 2; }
}
</style>
