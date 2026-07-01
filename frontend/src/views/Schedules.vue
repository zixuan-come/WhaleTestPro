<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { listSchedules, createSchedule, updateSchedule, deleteSchedule } from '../api/schedule'
import Modal from '../components/Modal.vue'

const items = ref([])
const loading = ref(true)
const error = ref('')

const showModal = ref(false)
const saving = ref(false)
const formErr = ref('')
const editingId = ref(null)
const form = reactive({ name: '', cron: '', tag: '', enabled: true })

const total = computed(() => items.value.length)
const enabledCount = computed(() => items.value.filter(s => s.enabled).length)

async function load() {
  loading.value = true
  error.value = ''
  try {
    items.value = await listSchedules()
  } catch (e) {
    error.value = e.message || '加载失败'
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editingId.value = null
  form.name = ''
  form.cron = ''
  form.tag = ''
  form.enabled = true
  formErr.value = ''
  showModal.value = true
}

function openEdit(s) {
  editingId.value = s.id
  form.name = s.name
  form.cron = s.cron
  form.tag = s.tag || ''
  form.enabled = s.enabled
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
  if (!form.cron.trim()) { formErr.value = '请填写 Cron 表达式'; return }

  const payload = {
    name: form.name.trim(),
    cron: form.cron.trim(),
    tag: form.tag.trim() || null,
    enabled: form.enabled,
  }

  saving.value = true
  try {
    if (editingId.value == null) await createSchedule(payload)
    else await updateSchedule(editingId.value, payload)
    showModal.value = false
    await load()
  } catch (e) {
    formErr.value = e.message || '保存失败'
  } finally {
    saving.value = false
  }
}

// 列表里直接切启用/停用:复用 update,只翻 enabled
async function toggleEnabled(s) {
  try {
    await updateSchedule(s.id, { name: s.name, cron: s.cron, tag: s.tag || null, enabled: !s.enabled })
    await load()
  } catch (e) {
    alert(e.message || '切换失败')
  }
}

async function onDelete(s) {
  if (!confirm(`确认删除定时任务「${s.name}」?`)) return
  try {
    await deleteSchedule(s.id)
    items.value = items.value.filter(i => i.id !== s.id)
  } catch (e) {
    alert(e.message || '删除失败')
  }
}

onMounted(load)
</script>

<template>
  <div class="cards">
    <div class="card"><div class="k">定时任务</div><div class="v pri">{{ total }}</div></div>
    <div class="card"><div class="k">启用中</div><div class="v pass">{{ enabledCount }}</div></div>
    <div class="card"><div class="k">已停用</div><div class="v">{{ total - enabledCount }}</div></div>
  </div>

  <div class="panel">
    <div class="panel-head">
      定时调度
      <button class="btn btn-primary" @click="openCreate">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14" /></svg>
        新建任务
      </button>
    </div>

    <div v-if="loading" class="state">加载中…</div>
    <div v-else-if="error" class="state err">{{ error }}<button class="btn btn-ghost retry" @click="load">重试</button></div>
    <div v-else-if="!items.length" class="state">暂无定时任务,点右上角「新建任务」创建</div>

    <template v-else>
      <div class="row head">
        <span class="c-name">任务</span>
        <span class="c-cron">Cron</span>
        <span class="c-tag">标签</span>
        <span class="c-status">状态</span>
        <span class="c-act">操作</span>
      </div>
      <div v-for="s in items" :key="s.id" class="row">
        <span class="c-name"><span class="id">#{{ s.id }}</span>{{ s.name }}</span>
        <span class="c-cron">{{ s.cron }}</span>
        <span class="c-tag"><span v-if="s.tag" class="tag">{{ s.tag }}</span><span v-else class="muted">全部</span></span>
        <span class="c-status">
          <span class="badge" :class="s.enabled ? 'b-pass' : 'b-skip'"><span class="dot"></span>{{ s.enabled ? '启用' : '停用' }}</span>
        </span>
        <span class="c-act">
          <button class="icon-btn" :title="s.enabled ? '停用' : '启用'" @click="toggleEnabled(s)">
            <svg v-if="s.enabled" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10 9v6M14 9v6M5 7h14v12a1 1 0 01-1 1H6a1 1 0 01-1-1V7Z" /></svg>
            <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 4l14 8-14 8V4Z" /></svg>
          </button>
          <button class="icon-btn edit" title="编辑" @click="openEdit(s)">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 20h9M16.5 3.5a2.1 2.1 0 013 3L7 19l-4 1 1-4 12.5-12.5Z" /></svg>
          </button>
          <button class="icon-btn del" title="删除" @click="onDelete(s)">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14" /></svg>
          </button>
        </span>
      </div>
    </template>
  </div>

  <!-- 新建/编辑任务弹层 -->
  <Modal v-if="showModal" :title="editingId == null ? '新建定时任务' : '编辑定时任务'" :max-width="520" :busy="saving" @close="closeModal">
    <div class="field">
      <label>任务名称</label>
      <input v-model="form.name" placeholder="如:每日冒烟回归" />
    </div>
    <div class="field">
      <label>Cron 表达式</label>
      <input v-model="form.cron" placeholder="0 2 * * *  (每天凌晨 2 点)" />
      <div class="tip">5 位标准 cron:分 时 日 月 周。</div>
    </div>
    <div class="field">
      <label>标签筛选 <span class="opt">(可选,不填跑全部)</span></label>
      <input v-model="form.tag" placeholder="smoke" />
    </div>
    <label class="chk">
      <input type="checkbox" v-model="form.enabled" />
      <span>创建后立即启用</span>
    </label>
    <div v-if="formErr" class="form-err">{{ formErr }}</div>

    <template #foot>
      <button class="btn btn-ghost" @click="closeModal" :disabled="saving">取消</button>
      <button class="btn btn-primary" @click="save" :disabled="saving">{{ saving ? '保存中…' : '保存' }}</button>
    </template>
  </Modal>
</template>

<style scoped>
.cards { display:grid; grid-template-columns:repeat(3,1fr); gap:16px; margin-bottom:24px; }
.card { background:var(--surface); border:1px solid var(--border);
  border-radius:14px; padding:18px 20px; box-shadow:var(--shadow-sm); transition:border-color .15s; }
.card:hover { border-color:var(--primary); }
.card .k { font-size:12px; color:var(--text-muted); margin-bottom:10px; font-weight:550; }
.card .v { font-size:27px; font-weight:780; letter-spacing:-.5px; }
.card .v.pass { color:var(--pass-fg); }
.card .v.pri { color:var(--primary); }

.row { display:grid; grid-template-columns:1.5fr 1.4fr 1fr 90px 118px; align-items:center; gap:12px;
  padding:13px 20px; border-bottom:1px solid var(--border); font-size:13px; transition:background .15s; }
.row:last-child { border-bottom:none; }
.row:not(.head):hover { background:var(--surface-2); }
.row.head { font-size:11.5px; font-weight:600; color:var(--text-muted);
  text-transform:uppercase; letter-spacing:.5px; background:var(--surface-2); }
.c-name { display:flex; align-items:center; gap:10px; font-weight:550; }
.c-name .id { color:var(--text-muted); font-family:ui-monospace,Consolas,monospace; font-size:12px;
  background:var(--surface-2); padding:2px 8px; border-radius:6px; flex:none; }
.c-cron { font-family:ui-monospace,Consolas,monospace; font-size:12.5px; color:var(--text-muted); }
.c-tag .tag { font-size:11px; padding:2px 8px; border-radius:6px; background:var(--surface-2);
  border:1px solid var(--border); color:var(--text-muted); }
.c-tag .muted { color:var(--text-muted); font-size:12px; }
.c-act { text-align:right; display:flex; gap:4px; justify-content:flex-end; }
.icon-btn { display:inline-flex; align-items:center; justify-content:center;
  width:32px; height:32px; padding:0; background:none; border:none; color:var(--text-muted);
  cursor:pointer; border-radius:4px; transition:color .15s,background .15s; }
.icon-btn svg { width:15px; height:15px; }
.icon-btn:hover { color:var(--primary); background:var(--surface-2); }
.icon-btn.edit:hover { color:var(--primary); background:var(--surface-2); }
.icon-btn.del:hover { color:var(--fail-fg); background:var(--fail-bg); }

.state { padding:48px 20px; text-align:center; color:var(--text-muted); font-size:13px; }
.state.err { color:var(--fail-fg); }
.retry { margin-left:12px; }

/* ===== 弹层 ===== */
.field { margin-bottom:18px; }
.field label { display:block; font-size:12.5px; font-weight:600; margin-bottom:8px; color:var(--text); }
.field label .opt { color:var(--text-muted); font-weight:400; }
.field input { width:100%; height:38px; padding:0 12px; font-size:13px; color:var(--text);
  background:var(--surface-2); border:1px solid var(--border); border-radius:8px;
  transition:border-color .15s; font-family:inherit; }
.field input:focus { outline:none; border-color:var(--primary); }
.field .tip { font-size:11.5px; color:var(--text-muted); margin-top:6px; }
.chk { display:flex; align-items:center; gap:8px; font-size:13px; color:var(--text); cursor:pointer; margin-bottom:4px; }
.chk input { width:16px; height:16px; accent-color:var(--primary); }

.form-err { color:var(--fail-fg); font-size:12.5px; background:var(--fail-bg); padding:9px 12px; border-radius:8px; margin-top:14px; }

/* ===== 响应式 ===== */
@media (max-width:1100px) {
  .cards { grid-template-columns:repeat(3,1fr); }
  .row { grid-template-columns:1.5fr 1.4fr 90px 118px; }
  .c-tag { display:none; }
}
@media (max-width:640px) {
  .cards { grid-template-columns:1fr; gap:12px; }
  .row { grid-template-columns:1fr 90px 118px; gap:8px; padding:12px 14px; }
  .c-cron { display:none; }
}
</style>
