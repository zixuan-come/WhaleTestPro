<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { listProjects, createProject, deleteProject } from '../api/project'
import { useAuthStore } from '../stores/auth'
import Modal from '../components/Modal.vue'

const auth = useAuthStore()
const items = ref([])
const loading = ref(true)
const error = ref('')

const showModal = ref(false)
const saving = ref(false)
const formErr = ref('')
const form = reactive({ name: '', description: '' })

const total = computed(() => items.value.length)

async function load() {
  loading.value = true
  error.value = ''
  try {
    items.value = await listProjects()
  } catch (e) {
    error.value = e.message || '加载失败'
  } finally {
    loading.value = false
  }
}

function openCreate() {
  form.name = ''
  form.description = ''
  formErr.value = ''
  showModal.value = true
}

function closeModal() {
  if (saving.value) return
  showModal.value = false
}

async function save() {
  formErr.value = ''
  if (!form.name.trim()) { formErr.value = '请填写项目名称'; return }

  saving.value = true
  try {
    const created = await createProject({
      name: form.name.trim(),
      description: form.description.trim() || null,
    })
    showModal.value = false
    // 建完顺手切到新项目 — 用户建完通常就想去它下面工作
    auth.setProject(created.id, created.name)
    await load()
  } catch (e) {
    formErr.value = e.message || '创建失败'
  } finally {
    saving.value = false
  }
}

async function onDelete(project) {
  const isCurrent = project.id === auth.currentProjectId
  const warn = isCurrent ? '\n\n⚠️ 这是你当前所在的项目,删除后需重新选择。' : ''
  if (!confirm(`确认删除项目「${project.name}」?此操作不可恢复。${warn}`)) return
  try {
    await deleteProject(project.id)
    items.value = items.value.filter(p => p.id !== project.id)
    // 删的是当前项目就清一下,下次守卫会重选或跳这里
    if (isCurrent) auth.setProject(null, '')
  } catch (e) {
    alert(e.message || '删除失败')
  }
}

function switchTo(project) {
  auth.setProject(project.id, project.name)
  // 顺手刷新一下让列表高亮生效(active class 通过 currentProjectId 计算)
}

function formatDate(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('zh-CN', { hour12: false })
}

onMounted(load)
</script>

<template>
  <div class="cards">
    <div class="card"><div class="k">项目总数</div><div class="v pri">{{ total }}</div></div>
    <div class="card"><div class="k">当前项目</div><div class="v">{{ auth.currentProjectName || '未选' }}</div></div>
  </div>

  <div class="panel">
    <div class="panel-head">
      项目列表
      <button class="btn btn-primary" @click="openCreate">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14" /></svg>
        新建项目
      </button>
    </div>

    <div v-if="loading" class="state">加载中…</div>
    <div v-else-if="error" class="state err">
      {{ error }}
      <button class="btn btn-ghost retry" @click="load">重试</button>
    </div>
    <div v-else-if="!items.length" class="state">
      还没有任何项目,点右上角「新建项目」创建第一个 —— 所有接口/用例/流量都会归到你选中的项目下。
    </div>

    <template v-else>
      <div class="row head">
        <span class="c-name">名称</span>
        <span class="c-desc">简介</span>
        <span class="c-time">创建时间</span>
        <span class="c-act">操作</span>
      </div>
      <div v-for="(p, i) in items" :key="p.id" class="row" :class="{ current: p.id === auth.currentProjectId }">
        <span class="c-name">
          <span class="id">#{{ i + 1 }}</span>{{ p.name }}
          <span v-if="p.id === auth.currentProjectId" class="badge">当前</span>
        </span>
        <span class="c-desc" :title="p.description">{{ p.description || '—' }}</span>
        <span class="c-time">{{ formatDate(p.created_at) }}</span>
        <span class="c-act">
          <button v-if="p.id !== auth.currentProjectId" class="btn btn-ghost sm" @click="switchTo(p)">切到这个</button>
          <button class="icon-btn" title="删除" @click="onDelete(p)">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14" />
            </svg>
          </button>
        </span>
      </div>
    </template>
  </div>

  <Modal v-if="showModal" title="新建项目" :busy="saving" @close="closeModal">
    <div class="field">
      <label>项目名称</label>
      <input v-model="form.name" placeholder="如:电商压测项目" />
    </div>
    <div class="field">
      <label>简介 <span class="opt">(可选)</span></label>
      <textarea v-model="form.description" rows="3" placeholder="这个项目是干嘛的,给未来的自己看"></textarea>
    </div>
    <div v-if="formErr" class="form-err">{{ formErr }}</div>

    <template #foot>
      <button class="btn btn-ghost" @click="closeModal" :disabled="saving">取消</button>
      <button class="btn btn-primary" @click="save" :disabled="saving">{{ saving ? '创建中…' : '创建' }}</button>
    </template>
  </Modal>
</template>

<style scoped>
.cards { display:grid; grid-template-columns:repeat(2,1fr); gap:16px; margin-bottom:24px; max-width:520px; }
.card { background:var(--surface); border:1px solid var(--border);
  border-radius:14px; padding:18px 20px; box-shadow:var(--shadow-sm); transition:border-color .15s; }
.card:hover { border-color:var(--primary); }
.card .k { font-size:12px; color:var(--text-muted); margin-bottom:10px; font-weight:550; }
.card .v { font-size:22px; font-weight:750; letter-spacing:-.3px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.card .v.pri { color:var(--primary); font-size:27px; }

.row { display:grid; grid-template-columns:1.5fr 2fr 1.4fr 170px; align-items:center; gap:12px;
  padding:13px 20px; border-bottom:1px solid var(--border); font-size:13px; transition:background .15s; }
.row:last-child { border-bottom:none; }
.row:not(.head):hover { background:var(--surface-2); }
.row.head { font-size:11.5px; font-weight:600; color:var(--text-muted);
  text-transform:uppercase; letter-spacing:.5px; background:var(--surface-2); }
.row.current { background:var(--surface-2); }
.c-name { display:flex; align-items:center; gap:10px; font-weight:600; }
.c-name .id { color:var(--text-muted); font-family:ui-monospace,Consolas,monospace; font-size:12px;
  background:var(--surface-2); padding:2px 8px; border-radius:6px; font-weight:400; }
.c-name .badge { background:var(--primary); color:#fff; font-size:10.5px; padding:2px 7px;
  border-radius:5px; font-weight:600; letter-spacing:.4px; }
.c-desc { color:var(--text-muted); font-size:12.5px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.c-time { color:var(--text-muted); font-family:ui-monospace,Consolas,monospace; font-size:12px; }
.c-act { text-align:right; display:flex; align-items:center; justify-content:flex-end; gap:8px; }

.btn.sm { padding:5px 11px; font-size:12px; }

.icon-btn { display:inline-flex; align-items:center; justify-content:center;
  width:32px; height:32px; padding:0; background:none; border:none; color:var(--text-muted);
  cursor:pointer; border-radius:4px; transition:color .15s,background .15s; }
.icon-btn svg { width:16px; height:16px; }
.icon-btn:hover { color:var(--fail-fg); background:var(--fail-bg); }

.state { padding:48px 20px; text-align:center; color:var(--text-muted); font-size:13px; max-width:560px; margin:0 auto; }
.state.err { color:var(--fail-fg); }
.retry { margin-left:12px; }

.field { margin-bottom:18px; }
.field label { display:block; font-size:12.5px; font-weight:600; margin-bottom:8px; color:var(--text); }
.field label .opt { color:var(--text-muted); font-weight:400; }
.field input, .field textarea { width:100%; padding:0 12px; font-size:13px; color:var(--text);
  background:var(--surface-2); border:1px solid var(--border); border-radius:8px;
  transition:border-color .15s; font-family:inherit; }
.field input { height:38px; }
.field textarea { padding:10px 12px; font-size:12.5px; resize:vertical; }
.field input:focus, .field textarea:focus { outline:none; border-color:var(--primary); }

.form-err { color:var(--fail-fg); font-size:12.5px; background:var(--fail-bg); padding:9px 12px; border-radius:8px; }

@media (max-width:900px) {
  .row { grid-template-columns:1.4fr 1.5fr 130px; gap:8px; padding:12px 14px; }
  .c-desc { display:none; }
}
@media (max-width:600px) {
  .cards { grid-template-columns:1fr; }
  .row { grid-template-columns:1fr 100px; }
  .c-time { display:none; }
}
</style>
