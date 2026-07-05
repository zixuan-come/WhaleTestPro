<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { listMocks, createMock, updateMock, deleteMock } from '../api/mock'
import { useAuthStore } from '../stores/auth'
import Modal from '../components/Modal.vue'

const auth = useAuthStore()
const items = ref([])
const loading = ref(true)
const error = ref('')

const showModal = ref(false)
const saving = ref(false)
const formErr = ref('')
const editingId = ref(null)      // null=新建, 数字=编辑
const form = reactive({ name: '', path: '', method: 'GET', status: 200, body: '', delay_ms: 0 })

const METHODS = ['GET', 'POST', 'PUT', 'DELETE', 'PATCH']
const total = computed(() => items.value.length)
// 挡板命中 URL 前缀:/mock/{pid} —— 后端多项目改造后,path 必须带 pid,展示时把前缀显式画出来
const hitUrlPrefix = computed(() => `/mock/${auth.currentProjectId ?? '?'}`)

function methodClass(m) { return 'm-' + (m || 'get').toLowerCase() }

async function load() {
  loading.value = true
  error.value = ''
  try {
    items.value = await listMocks()
  } catch (e) {
    error.value = e.message || '加载失败'
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editingId.value = null
  form.name = ''
  form.path = ''
  form.method = 'GET'
  form.status = 200
  form.body = ''
  form.delay_ms = 0
  formErr.value = ''
  showModal.value = true
}

function openEdit(m) {
  editingId.value = m.id
  form.name = m.name
  form.path = m.path
  form.method = m.method
  form.status = m.status
  form.body = m.body ? JSON.stringify(m.body, null, 2) : ''
  form.delay_ms = m.delay_ms || 0
  formErr.value = ''
  showModal.value = true
}

function closeModal() {
  if (saving.value) return
  showModal.value = false
}

async function save() {
  formErr.value = ''
  if (!form.name.trim()) { formErr.value = '请填写规则名称'; return }
  if (!form.path.trim()) { formErr.value = '请填写匹配路径'; return }

  let body = null
  const s = form.body.trim()
  if (s) {
    try { body = JSON.parse(s) } catch { formErr.value = '响应 Body 不是合法 JSON'; return }
  }

  const payload = {
    name: form.name.trim(),
    path: form.path.trim(),
    method: form.method,
    status: Number(form.status) || 200,
    body,
    delay_ms: Number(form.delay_ms) || 0,
  }

  saving.value = true
  try {
    if (editingId.value == null) await createMock(payload)
    else await updateMock(editingId.value, payload)
    showModal.value = false
    await load()
  } catch (e) {
    formErr.value = e.message || '保存失败'
  } finally {
    saving.value = false
  }
}

async function onDelete(m) {
  if (!confirm(`确认删除挡板规则「${m.name}」?`)) return
  try {
    await deleteMock(m.id)
    items.value = items.value.filter(i => i.id !== m.id)
  } catch (e) {
    alert(e.message || '删除失败')
  }
}

onMounted(load)
</script>

<template>
  <div class="cards">
    <div class="card"><div class="k">挡板规则</div><div class="v pri">{{ total }}</div></div>
    <div class="card"><div class="k">命中入口</div><div class="v mono">{{ hitUrlPrefix }}/*</div></div>
  </div>

  <div class="panel">
    <div class="panel-head">
      Mock 挡板
      <button class="btn btn-primary" @click="openCreate">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14" /></svg>
        新建挡板
      </button>
    </div>

    <div v-if="loading" class="state">加载中…</div>
    <div v-else-if="error" class="state err">{{ error }}<button class="btn btn-ghost retry" @click="load">重试</button></div>
    <div v-else-if="!items.length" class="state">暂无挡板规则,点右上角「新建挡板」创建</div>

    <template v-else>
      <div class="row head">
        <span class="c-method">方法</span>
        <span class="c-name">名称</span>
        <span class="c-path">匹配路径</span>
        <span class="c-status">状态码</span>
        <span class="c-delay">延迟</span>
        <span class="c-act">操作</span>
      </div>
      <div v-for="(m, i) in items" :key="m.id" class="row">
        <span class="c-method"><span class="tag-method" :class="methodClass(m.method)">{{ (m.method || 'GET').toUpperCase() }}</span></span>
        <span class="c-name"><span class="id">#{{ i + 1 }}</span>{{ m.name }}</span>
        <span class="c-path" :title="hitUrlPrefix + m.path"><span class="url-prefix">{{ hitUrlPrefix }}</span>{{ m.path }}</span>
        <span class="c-status">{{ m.status }}</span>
        <span class="c-delay">{{ m.delay_ms ? m.delay_ms + ' ms' : '—' }}</span>
        <span class="c-act">
          <button class="icon-btn edit" title="编辑" @click="openEdit(m)">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 20h9M16.5 3.5a2.1 2.1 0 013 3L7 19l-4 1 1-4 12.5-12.5Z" /></svg>
          </button>
          <button class="icon-btn del" title="删除" @click="onDelete(m)">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14" /></svg>
          </button>
        </span>
      </div>
    </template>
  </div>

  <!-- 新建/编辑挡板弹层 -->
  <Modal v-if="showModal" :title="editingId == null ? '新建挡板规则' : '编辑挡板规则'" :busy="saving" @close="closeModal">
    <div class="field">
      <label>规则名称</label>
      <input v-model="form.name" placeholder="如:订单服务不可用" />
    </div>
    <div class="grid-mu">
      <div class="field">
        <label>方法</label>
        <select v-model="form.method">
          <option v-for="m in METHODS" :key="m" :value="m">{{ m }}</option>
        </select>
      </div>
      <div class="field">
        <label>匹配路径</label>
        <input v-model="form.path" placeholder="/orders/123" />
      </div>
    </div>
    <div class="grid2">
      <div class="field">
        <label>返回状态码</label>
        <input v-model.number="form.status" type="number" />
      </div>
      <div class="field">
        <label>延迟 (毫秒)</label>
        <input v-model.number="form.delay_ms" type="number" min="0" />
      </div>
    </div>
    <div class="field">
      <label>响应 Body <span class="opt">(JSON,可选)</span></label>
      <textarea v-model="form.body" rows="4" placeholder='{"code": 500, "msg": "service down"}'></textarea>
    </div>
    <div v-if="formErr" class="form-err">{{ formErr }}</div>

    <template #foot>
      <button class="btn btn-ghost" @click="closeModal" :disabled="saving">取消</button>
      <button class="btn btn-primary" @click="save" :disabled="saving">{{ saving ? '保存中…' : '保存' }}</button>
    </template>
  </Modal>
</template>

<style scoped>
.cards { display:grid; grid-template-columns:repeat(4,1fr); gap:16px; margin-bottom:24px; }
.card { background:var(--surface); border:1px solid var(--border);
  border-radius:14px; padding:18px 20px; box-shadow:var(--shadow-sm); transition:border-color .15s; }
.card:hover { border-color:var(--primary); }
.card .k { font-size:12px; color:var(--text-muted); margin-bottom:10px; font-weight:550; }
.card .v { font-size:27px; font-weight:780; letter-spacing:-.5px; }
.card .v.pri { color:var(--primary); }
.card .v.mono { font-size:20px; font-family:ui-monospace,Consolas,monospace; }

.row { display:grid; grid-template-columns:80px 1.4fr 1.6fr 80px 80px 84px; align-items:center; gap:12px;
  padding:13px 20px; border-bottom:1px solid var(--border); font-size:13px; transition:background .15s; }
.row:last-child { border-bottom:none; }
.row:not(.head):hover { background:var(--surface-2); }
.row.head { font-size:11.5px; font-weight:600; color:var(--text-muted);
  text-transform:uppercase; letter-spacing:.5px; background:var(--surface-2); }
.c-name { display:flex; align-items:center; gap:10px; font-weight:550; }
.c-name .id { color:var(--text-muted); font-family:ui-monospace,Consolas,monospace; font-size:12px;
  background:var(--surface-2); padding:2px 8px; border-radius:6px; flex:none; }
.c-path { color:var(--text-muted); font-family:ui-monospace,Consolas,monospace; font-size:12px;
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.c-path .url-prefix { color:var(--text-muted); opacity:.55; }
.c-status, .c-delay { font-family:ui-monospace,Consolas,monospace; font-size:12.5px; }
.c-act { text-align:right; display:flex; gap:4px; justify-content:flex-end; }
.icon-btn { display:inline-flex; align-items:center; justify-content:center;
  width:32px; height:32px; padding:0; background:none; border:none; color:var(--text-muted);
  cursor:pointer; border-radius:4px; transition:color .15s,background .15s; }
.icon-btn svg { width:15px; height:15px; }
.icon-btn.edit:hover { color:var(--primary); background:var(--surface-2); }
.icon-btn.del:hover { color:var(--fail-fg); background:var(--fail-bg); }

.state { padding:48px 20px; text-align:center; color:var(--text-muted); font-size:13px; }
.state.err { color:var(--fail-fg); }
.retry { margin-left:12px; }

/* ===== 弹层 ===== */
.grid-mu { display:grid; grid-template-columns:120px 1fr; gap:14px; }
.grid2 { display:grid; grid-template-columns:1fr 1fr; gap:14px; }
.field { margin-bottom:18px; }
.field label { display:block; font-size:12.5px; font-weight:600; margin-bottom:8px; color:var(--text); }
.field label .opt { color:var(--text-muted); font-weight:400; }
.field input, .field select, .field textarea { width:100%; padding:0 12px; font-size:13px; color:var(--text);
  background:var(--surface-2); border:1px solid var(--border); border-radius:8px;
  transition:border-color .15s; font-family:inherit; }
.field input, .field select { height:38px; }
.field textarea { padding:10px 12px; font-family:ui-monospace,Consolas,monospace; font-size:12.5px; resize:vertical; }
.field input:focus, .field select:focus, .field textarea:focus { outline:none; border-color:var(--primary); }

.form-err { color:var(--fail-fg); font-size:12.5px; background:var(--fail-bg); padding:9px 12px; border-radius:8px; }

/* ===== 响应式 ===== */
@media (max-width:1100px) {
  .cards { grid-template-columns:repeat(2,1fr); }
  .row { grid-template-columns:80px 1.4fr 80px 84px; }
  .c-path, .c-delay { display:none; }
}
@media (max-width:640px) {
  .cards { grid-template-columns:1fr; gap:12px; }
  .row { grid-template-columns:64px 1fr 84px; gap:8px; padding:12px 14px; }
  .c-status { display:none; }
  .grid-mu, .grid2 { grid-template-columns:1fr; }
}
</style>
