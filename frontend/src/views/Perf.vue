<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import {
  listPerfTasks, createPerfTask, deletePerfTask, runPerfTask,
} from '../api/perf'
import Modal from '../components/Modal.vue'

const items = ref([])
const loading = ref(true)
const error = ref('')

const showModal = ref(false)
const saving = ref(false)
const formErr = ref('')
const runningId = ref(null)      // 正在触发运行的任务 id
const form = reactive({ name: '', target_host: '', target_path: '', users: 10, spawn_rate: 2, duration: 30 })

const total = computed(() => items.value.length)
const runningCount = computed(() => items.value.filter(t => t.status === 'running').length)
const doneCount = computed(() => items.value.filter(t => t.status === 'done').length)
const maxRps = computed(() => {
  const vals = items.value.map(t => t.rps).filter(v => v != null)
  return vals.length ? Math.max(...vals).toFixed(1) : '—'
})

const STATUS_TEXT = { pending: '待运行', running: '运行中', done: '已完成' }
function statusText(s) { return STATUS_TEXT[s] || s || '—' }
function statusClass(s) {
  if (s === 'done') return 'b-pass'
  if (s === 'running') return 'b-warn'
  return 'b-skip'
}

function fmtRps(v) { return v == null ? '—' : v.toFixed(1) }
function fmtMs(v) { return v == null ? '—' : Math.round(v) + ' ms' }
function fmtFail(v) { return v == null ? '—' : (v * 100).toFixed(1) + '%' }

async function load() {
  loading.value = true
  error.value = ''
  try {
    items.value = await listPerfTasks()
  } catch (e) {
    error.value = e.message || '加载失败'
  } finally {
    loading.value = false
  }
}

function openCreate() {
  form.name = ''
  form.target_host = ''
  form.target_path = ''
  form.users = 10
  form.spawn_rate = 2
  form.duration = 30
  formErr.value = ''
  showModal.value = true
}

function closeModal() {
  if (saving.value) return
  showModal.value = false
}

async function save() {
  formErr.value = ''
  if (!form.name.trim()) { formErr.value = '请填写任务名称'; return }
  if (!form.target_host.trim()) { formErr.value = '请填写目标 Host'; return }
  if (!form.target_path.trim()) { formErr.value = '请填写目标路径'; return }
  if (!(form.users > 0) || !(form.spawn_rate > 0) || !(form.duration > 0)) {
    formErr.value = '并发数 / 每秒启动 / 持续时长都要大于 0'; return
  }

  saving.value = true
  try {
    await createPerfTask({
      name: form.name.trim(),
      target_host: form.target_host.trim(),
      target_path: form.target_path.trim(),
      users: Number(form.users),
      spawn_rate: Number(form.spawn_rate),
      duration: Number(form.duration),
    })
    showModal.value = false
    await load()
  } catch (e) {
    formErr.value = e.message || '保存失败'
  } finally {
    saving.value = false
  }
}

async function onRun(task) {
  runningId.value = task.id
  try {
    const updated = await runPerfTask(task.id)
    // 后端把状态标成 running 并返回;就地更新该行,压测本身异步跑,稍后刷新看结果
    const i = items.value.findIndex(t => t.id === task.id)
    if (i !== -1 && updated) items.value[i] = updated
  } catch (e) {
    alert(e.message || '启动失败')
  } finally {
    runningId.value = null
  }
}

async function onDelete(task) {
  if (!confirm(`确认删除压测任务「${task.name}」?`)) return
  try {
    await deletePerfTask(task.id)
    items.value = items.value.filter(t => t.id !== task.id)
  } catch (e) {
    alert(e.message || '删除失败')
  }
}

onMounted(load)
</script>

<template>
  <div class="cards">
    <div class="card"><div class="k">压测任务</div><div class="v pri">{{ total }}</div></div>
    <div class="card"><div class="k">运行中</div><div class="v warn">{{ runningCount }}</div></div>
    <div class="card"><div class="k">已完成</div><div class="v pass">{{ doneCount }}</div></div>
    <div class="card"><div class="k">峰值 RPS</div><div class="v">{{ maxRps }}</div></div>
  </div>

  <div class="panel">
    <div class="panel-head">
      压测任务
      <button class="btn btn-primary" @click="openCreate">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14" /></svg>
        新建压测
      </button>
    </div>

    <div v-if="loading" class="state">加载中…</div>
    <div v-else-if="error" class="state err">
      {{ error }}
      <button class="btn btn-ghost retry" @click="load">重试</button>
    </div>
    <div v-else-if="!items.length" class="state">暂无压测任务,点右上角「新建压测」创建</div>

    <template v-else>
      <div class="row head">
        <span class="c-name">任务</span>
        <span class="c-target">目标</span>
        <span class="c-load">并发 · 时长</span>
        <span class="c-status">状态</span>
        <span class="c-rps">RPS</span>
        <span class="c-ms">平均耗时</span>
        <span class="c-fail">失败率</span>
        <span class="c-act">操作</span>
      </div>
      <div v-for="t in items" :key="t.id" class="row">
        <span class="c-name"><span class="id">#{{ t.id }}</span>{{ t.name }}</span>
        <span class="c-target" :title="t.target_host + t.target_path">{{ t.target_host }}{{ t.target_path }}</span>
        <span class="c-load">{{ t.users }} VU · {{ t.duration }}s</span>
        <span class="c-status"><span class="badge" :class="statusClass(t.status)"><span class="dot"></span>{{ statusText(t.status) }}</span></span>
        <span class="c-rps">{{ fmtRps(t.rps) }}</span>
        <span class="c-ms">{{ fmtMs(t.avg_response_ms) }}</span>
        <span class="c-fail" :class="{ bad: t.fail_ratio > 0 }">{{ fmtFail(t.fail_ratio) }}</span>
        <span class="c-act">
          <button class="icon-btn run" title="运行" :disabled="t.status === 'running' || runningId === t.id" @click="onRun(t)">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 4l14 8-14 8V4Z" /></svg>
          </button>
          <button class="icon-btn del" title="删除" @click="onDelete(t)">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14" /></svg>
          </button>
        </span>
      </div>
    </template>
  </div>

  <!-- 新建压测弹层 -->
  <Modal v-if="showModal" title="新建压测任务" :busy="saving" @close="closeModal">
    <div class="field">
      <label>任务名称</label>
      <input v-model="form.name" placeholder="如:下单接口 200 并发" />
    </div>
    <div class="grid2">
      <div class="field">
        <label>目标 Host</label>
        <input v-model="form.target_host" placeholder="https://api.example.com" />
      </div>
      <div class="field">
        <label>目标路径</label>
        <input v-model="form.target_path" placeholder="/orders" />
      </div>
    </div>
    <div class="grid3">
      <div class="field">
        <label>并发用户 VU</label>
        <input v-model.number="form.users" type="number" min="1" />
      </div>
      <div class="field">
        <label>每秒启动</label>
        <input v-model.number="form.spawn_rate" type="number" min="1" />
      </div>
      <div class="field">
        <label>持续时长 s</label>
        <input v-model.number="form.duration" type="number" min="1" />
      </div>
    </div>
    <div v-if="formErr" class="form-err">{{ formErr }}</div>

    <template #foot>
      <button class="btn btn-ghost" @click="closeModal" :disabled="saving">取消</button>
      <button class="btn btn-primary" @click="save" :disabled="saving">{{ saving ? '创建中…' : '创建' }}</button>
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
.card .v.pass { color:var(--pass-fg); }
.card .v.warn { color:var(--warn-fg); }
.card .v.pri { color:var(--primary); }

.row { display:grid; grid-template-columns:1.3fr 1.7fr 118px 88px 64px 88px 72px 76px; align-items:center; gap:10px;
  padding:13px 20px; border-bottom:1px solid var(--border); font-size:13px; transition:background .15s; }
.row:last-child { border-bottom:none; }
.row:not(.head):hover { background:var(--surface-2); }
.row.head { font-size:11px; font-weight:600; color:var(--text-muted);
  text-transform:uppercase; letter-spacing:.4px; background:var(--surface-2); }
.c-name { display:flex; align-items:center; gap:9px; font-weight:550; }
.c-name .id { color:var(--text-muted); font-family:ui-monospace,Consolas,monospace; font-size:12px;
  background:var(--surface-2); padding:2px 8px; border-radius:6px; flex:none; }
.c-target { color:var(--text-muted); font-family:ui-monospace,Consolas,monospace; font-size:12px;
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.c-load { color:var(--text-muted); font-size:12px; }
.c-rps, .c-ms, .c-fail { font-family:ui-monospace,Consolas,monospace; font-size:12.5px; font-weight:600; }
.c-fail.bad { color:var(--fail-fg); }
.c-act { text-align:right; display:flex; gap:4px; justify-content:flex-end; }
.icon-btn { display:inline-flex; align-items:center; justify-content:center;
  width:32px; height:32px; padding:0; background:none; border:none; color:var(--text-muted);
  cursor:pointer; border-radius:4px; transition:color .15s,background .15s; }
.icon-btn svg { width:15px; height:15px; }
.icon-btn.run:hover { color:var(--pass-fg); background:var(--pass-bg); }
.icon-btn.del:hover { color:var(--fail-fg); background:var(--fail-bg); }
.icon-btn:disabled { opacity:.4; cursor:not-allowed; }

.state { padding:48px 20px; text-align:center; color:var(--text-muted); font-size:13px; }
.state.err { color:var(--fail-fg); }
.retry { margin-left:12px; }

/* ===== 弹层 ===== */
.grid2 { display:grid; grid-template-columns:1fr 1fr; gap:14px; }
.grid3 { display:grid; grid-template-columns:1fr 1fr 1fr; gap:14px; }
.field { margin-bottom:18px; }
.field label { display:block; font-size:12.5px; font-weight:600; margin-bottom:8px; color:var(--text); }
.field input { width:100%; height:38px; padding:0 12px; font-size:13px; color:var(--text);
  background:var(--surface-2); border:1px solid var(--border); border-radius:8px;
  transition:border-color .15s; font-family:inherit; }
.field input:focus { outline:none; border-color:var(--primary); }

.form-err { color:var(--fail-fg); font-size:12.5px; background:var(--fail-bg); padding:9px 12px; border-radius:8px; }

/* ===== 响应式 ===== */
@media (max-width:1100px) {
  .cards { grid-template-columns:repeat(2,1fr); }
  .row { grid-template-columns:1.2fr 100px 80px 64px 72px 76px; }
  .c-target, .c-ms { display:none; }
}
@media (max-width:640px) {
  .cards { grid-template-columns:1fr; gap:12px; }
  .row { grid-template-columns:1fr 72px 64px 76px; gap:8px; padding:12px 14px; }
  .c-load, .c-fail { display:none; }
  .grid2, .grid3 { grid-template-columns:1fr; }
}
</style>
