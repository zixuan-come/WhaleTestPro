<script setup>
import { useFeedback } from '../composables/feedback'
const { showMessage, confirmAction } = useFeedback()
import { ref, reactive, computed, watch, onBeforeUnmount } from 'vue'
import { useAuthStore } from '../stores/auth'
import { listSchedules, createSchedule, updateSchedule, deleteSchedule } from '../api/schedule'
import { listEnvironments } from '../api/environment'
import Modal from '../components/Modal.vue'
import { scheduleTime } from '../utils/scheduleTime'

const items = ref([])
const props = defineProps({ catalog: { type: Object, default: () => ({ suites: [], cases: [] }) }, active: Boolean })
const emit = defineEmits(['create', 'edit', 'saved'])
const auth = useAuthStore()
const context = computed(() => `${auth.username}:${auth.currentProjectId}:${auth.token}`)
let version = 0
const pendingIds = ref([])
const environments = ref([])
const loading = ref(true)
const error = ref('')

function targetLabel(row) {
  if (row.selection) {
    const source = row.selection.mode === 'suite' ? props.catalog.suites : props.catalog.cases
    return row.selection.ids.map(id => source.find(item => item.id === id)?.name || `已删除的${row.selection.mode === 'suite' ? '套件' : '用例'} #${id}`).join('、')
  }
  return row.suite_id ? props.catalog.suites.find(item => item.id === row.suite_id)?.name || `套件 #${row.suite_id}` : row.tag ? `标签：${row.tag}（动态匹配）` : '全部用例（旧规则）'
}
const environmentName = id => environments.value.find(env => env.id === id)?.name || '未配置环境'

// ===== cron 友好构造:选频率+时间,自动拼 cron;custom 档才手写 =====
const FREQS = [
  { key: 'hourly', label: '每小时' },
  { key: 'daily', label: '每天' },
  { key: 'weekly', label: '每周' },
  { key: 'monthly', label: '每月' },
  { key: 'custom', label: '自定义 cron' },
]
// cron 星期:0/7=周日,1=周一…6=周六
const DOW = [
  { v: '1', label: '周一' }, { v: '2', label: '周二' }, { v: '3', label: '周三' },
  { v: '4', label: '周四' }, { v: '5', label: '周五' }, { v: '6', label: '周六' }, { v: '0', label: '周日' },
]
const cronUi = reactive({ freq: 'daily', minute: 0, hour: 2, dow: '1', dom: 1 })
const pad = (n) => String(n).padStart(2, '0')

// 由预设拼出的 cron(custom 档回传当前手写值,不覆盖)
const builtCron = computed(() => {
  const m = cronUi.minute, h = cronUi.hour
  switch (cronUi.freq) {
    case 'hourly': return `${m} * * * *`
    case 'daily': return `${m} ${h} * * *`
    case 'weekly': return `${m} ${h} * * ${cronUi.dow}`
    case 'monthly': return `${m} ${h} ${cronUi.dom} * *`
    default: return form.cron
  }
})
// 预设档:pickers 一变就同步进真正提交的 form.cron;custom 档保留手写
watch(builtCron, (v) => { if (cronUi.freq !== 'custom') form.cron = v })

function dowLabel(v) {
  const x = DOW.find(d => d.v === String(v))
  return x ? x.label.slice(1) : v   // '周一' → '一'
}
// custom 档:粗校验 5 段 + 各段取值范围,给人话/报错(前端体验,后端仍自校验)
function describeCron(expr) {
  const parts = (expr || '').trim().split(/\s+/)
  if (parts.length !== 5) return { ok: false, text: '需为 5 段:分 时 日 月 周' }
  const inRange = (s, lo, hi) => s.split(/[,\-/]/).every(t => t === '*' || (/^\d+$/.test(t) && +t >= lo && +t <= hi))
  const [mi, ho, dom, mo, dw] = parts
  if (!inRange(mi, 0, 59)) return { ok: false, text: '分钟应为 0-59' }
  if (!inRange(ho, 0, 23)) return { ok: false, text: '小时应为 0-23' }
  if (!inRange(dom, 1, 31)) return { ok: false, text: '日应为 1-31' }
  if (!inRange(mo, 1, 12)) return { ok: false, text: '月应为 1-12' }
  if (!inRange(dw, 0, 7)) return { ok: false, text: '周应为 0-7' }
  return { ok: true, text: `cron: ${parts.join(' ')}` }
}
// 实时人话预览
const cronPreview = computed(() => {
  const t = `${pad(cronUi.hour)}:${pad(cronUi.minute)}`
  switch (cronUi.freq) {
    case 'hourly': return { ok: true, text: `每小时的第 ${cronUi.minute} 分执行` }
    case 'daily': return { ok: true, text: `每天 ${t} 执行` }
    case 'weekly': return { ok: true, text: `每周${dowLabel(cronUi.dow)} ${t} 执行` }
    case 'monthly': return { ok: true, text: `每月 ${cronUi.dom} 号 ${t} 执行` }
    default: return describeCron(form.cron)
  }
})
// 编辑已有任务:尽量把 cron 反解回预设档,认不出就落 custom 原样保留
function loadCronToUi(expr) {
  const p = (expr || '').trim().split(/\s+/)
  const num = (s) => /^\d+$/.test(s)
  if (p.length === 5) {
    const [mi, ho, dom, mo, dw] = p
    if (mo === '*') {
      if (ho === '*' && dom === '*' && dw === '*' && num(mi)) { Object.assign(cronUi, { freq: 'hourly', minute: +mi }); return }
      if (dom === '*' && dw === '*' && num(mi) && num(ho)) { Object.assign(cronUi, { freq: 'daily', minute: +mi, hour: +ho }); return }
      if (dom === '*' && num(dw) && num(mi) && num(ho)) { Object.assign(cronUi, { freq: 'weekly', minute: +mi, hour: +ho, dow: dw }); return }
      if (dw === '*' && num(dom) && num(mi) && num(ho)) { Object.assign(cronUi, { freq: 'monthly', minute: +mi, hour: +ho, dom: +dom }); return }
    }
  }
  cronUi.freq = 'custom'
}

const showModal = ref(false)
const saving = ref(false)
const formErr = ref('')
const editingId = ref(null)
const form = reactive({ name: '', cron: '', tag: null, suite_id: null, env_id: null, enabled: true, selection: null, notify: false })

const total = computed(() => items.value.length)
const enabledCount = computed(() => items.value.filter(s => s.enabled).length)

async function load() {
  const request = ++version, key = context.value
  loading.value = true
  error.value = ''
  try {
    const [ss, envs] = await Promise.all([listSchedules(), listEnvironments()])
    if (request !== version || key !== context.value) return
    items.value = ss
    environments.value = envs
  } catch (e) {
    if (request === version && key === context.value) error.value = e.message || '加载失败'
  } finally {
    if (request === version) loading.value = false
  }
}

function openTiming(row, selection, notify) {
  editingId.value = row?.id || null
  Object.assign(form, { name: row?.name || '', tag: null, suite_id: null,
    env_id: selection.env_id, enabled: row?.enabled ?? true,
    selection: { mode: selection.mode, ids: [...selection.ids] }, notify: !!notify })
  Object.assign(cronUi, { freq: 'daily', minute: 0, hour: 2, dow: '1', dom: 1 })
  form.cron = row?.cron || builtCron.value
  if (row) loadCronToUi(row.cron)
  formErr.value = ''
  showModal.value = true
}

function closeModal() {
  if (saving.value) return
  showModal.value = false
}

async function save() {
  if (saving.value) return
  const key = context.value
  formErr.value = ''
  if (!form.name.trim()) { formErr.value = '请填写任务名称'; return }
  if (!form.env_id) { formErr.value = '请选择执行环境；没有环境时请先创建环境'; return }
  if (!form.cron.trim()) { formErr.value = '请填写 Cron 表达式'; return }
  if (cronUi.freq === 'custom' && !cronPreview.value.ok) { formErr.value = 'Cron 表达式非法:' + cronPreview.value.text; return }

  const payload = {
    name: form.name.trim(),
    cron: form.cron.trim(),
    tag: null,
    suite_id: null,
    env_id: form.env_id,
    enabled: form.enabled,
    selection: form.selection,
    notify: form.notify,
  }

  saving.value = true
  try {
    if (editingId.value == null) await createSchedule(payload)
    else await updateSchedule(editingId.value, payload)
    if (key !== context.value) return
    showModal.value = false
    showMessage('定时任务已保存')
    emit('saved')
    await load()
  } catch (e) {
    if (key === context.value) formErr.value = e.message || '保存失败'
  } finally {
    saving.value = false
  }
}

// 列表里直接切启用/停用:复用 update,只翻 enabled
async function toggleEnabled(s) {
  if (pendingIds.value.includes(s.id)) return
  const key = context.value
  pendingIds.value = [...pendingIds.value, s.id]
  try {
    if (!s.env_id) { emit('edit', s); showMessage('请先选择执行环境', 'error'); return }
    await updateSchedule(s.id, { name: s.name, cron: s.cron, tag: s.tag || null, suite_id: s.suite_id, env_id: s.env_id, selection: s.selection || null, notify: !!s.notify, enabled: !s.enabled })
    if (key === context.value) await load()
  } catch (e) {
    if (key === context.value) showMessage(e.message || '切换失败', 'error')
  } finally { pendingIds.value = pendingIds.value.filter(id => id !== s.id) }
}

async function onDelete(s) {
  const key = context.value
  if (!(await confirmAction(`确认删除定时任务「${s.name}」?`))) return
  if (key !== context.value) return
  try {
    await deleteSchedule(s.id)
    if (key === context.value) items.value = items.value.filter(i => i.id !== s.id)
  } catch (e) {
    showMessage(e.message || '删除失败', 'error')
  }
}

watch([context, () => props.active], () => {
  version++; items.value = []; showModal.value = false; formErr.value = ''
  if (props.active && auth.currentProjectId) load()
}, { immediate: true })
onBeforeUnmount(() => { version++ })
defineExpose({ openTiming })
</script>

<template>
  <div class="cards">
    <div class="card"><div class="k">定时任务</div><div class="v pri">{{ total }}</div></div>
    <div class="card"><div class="k">启用中</div><div class="v pass">{{ enabledCount }}</div></div>
    <div class="card"><div class="k">已停用</div><div class="v">{{ total - enabledCount }}</div></div>
  </div>

  <div class="panel">
    <div class="panel-head">
      定时回归任务
      <button class="btn btn-primary" @click="emit('create')">
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
        <span class="c-cron">执行规则</span>
        <span class="c-tag">测试内容 · 环境</span>
        <span class="c-status">状态</span>
        <span class="c-act">操作</span>
      </div>
      <div v-for="(s, i) in items" :key="s.id" class="row">
        <span class="c-name"><span class="id">#{{ i + 1 }}</span>{{ s.name }}</span>
        <details class="c-cron cron-rule"><summary :title="'点击查看 Cron：' + s.cron">{{ scheduleTime(s.cron) }}</summary><code>{{ s.cron }}</code></details>
        <span class="c-tag target-summary"><span :title="targetLabel(s)">{{ targetLabel(s) }}</span><small>{{ environmentName(s.env_id) }}</small></span>
        <span class="c-status">
          <span class="badge" :class="s.enabled ? 'b-pass' : 'b-skip'"><span class="dot"></span>{{ s.enabled ? '启用' : '停用' }}</span>
          <small v-if="s.sync_status !== 'synced'" class="sync-warning">{{ s.sync_status === 'error' ? '同步失败，请稍后重试' : '同步中' }}</small>
        </span>
        <span class="c-act">
          <RouterLink class="icon-btn" title="查看报告" :to="{ path: '/reports', query: { kind: !s.selection && s.suite_id ? 'suite' : 'regression', ...(s.selection ? { q: s.name } : {}) } }"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M8 7h8M8 12h8M8 17h5M5 3h14v18H5z" /></svg></RouterLink>
          <button class="icon-btn" :disabled="pendingIds.includes(s.id)" :title="s.enabled ? '停用' : '启用'" @click="toggleEnabled(s)">
            <svg v-if="s.enabled" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10 9v6M14 9v6M5 7h14v12a1 1 0 01-1 1H6a1 1 0 01-1-1V7Z" /></svg>
            <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 4l14 8-14 8V4Z" /></svg>
          </button>
          <button class="icon-btn edit" title="编辑" @click="emit('edit', s)">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 20h9M16.5 3.5a2.1 2.1 0 013 3L7 19l-4 1 1-4 12.5-12.5Z" /></svg>
          </button>
          <button class="icon-btn del" title="删除" @click="onDelete(s)">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14" /></svg>
          </button>
        </span>
      </div>
      <p class="schedule-time-note">执行规则按调度服务时区计算，点击规则可查看 Cron 表达式。</p>
    </template>
  </div>

  <!-- 新建/编辑任务弹层 -->
  <Modal v-if="showModal" :title="editingId == null ? '新建定时任务' : '编辑定时任务'" :max-width="560" :hide-scrollbar="true" :busy="saving" @close="closeModal">
    <div class="timing-summary">已选 {{ form.selection?.ids.length }} {{ form.selection?.mode === 'suite' ? '个套件' : '个用例' }} · {{ environmentName(form.env_id) }}<small>保存后按最新测试配置执行，报告归入回归测试。</small></div>
    <div class="field">
      <label for="schedule-name">任务名称</label>
      <input id="schedule-name" maxlength="100" v-model="form.name" placeholder="如:每日冒烟回归" />
    </div>
    <div class="field">
      <label for="schedule-frequency">执行频率</label>
      <select id="schedule-frequency" v-model="cronUi.freq">
        <option v-for="f in FREQS" :key="f.key" :value="f.key">{{ f.label }}</option>
      </select>
    </div>


    <div class="field time-row" v-if="cronUi.freq !== 'custom'">
      <template v-if="cronUi.freq === 'weekly'">
        <select v-model="cronUi.dow" class="seg">
          <option v-for="d in DOW" :key="d.v" :value="d.v">{{ d.label }}</option>
        </select>
      </template>
      <template v-if="cronUi.freq === 'monthly'">
        <select v-model.number="cronUi.dom" class="seg">
          <option v-for="d in 31" :key="d" :value="d">{{ d }} 号</option>
        </select>
      </template>
      <template v-if="cronUi.freq === 'hourly'">
        <span class="lbl">每小时的第</span>
        <select v-model.number="cronUi.minute" class="seg">
          <option v-for="m in 60" :key="m - 1" :value="m - 1">{{ m - 1 }}</option>
        </select>
        <span class="lbl">分</span>
      </template>
      <template v-else>
        <span class="lbl">时刻</span>
        <select v-model.number="cronUi.hour" class="seg">
          <option v-for="h in 24" :key="h - 1" :value="h - 1">{{ String(h - 1).padStart(2, '0') }}</option>
        </select>
        <span class="colon">:</span>
        <select v-model.number="cronUi.minute" class="seg">
          <option v-for="m in 60" :key="m - 1" :value="m - 1">{{ String(m - 1).padStart(2, '0') }}</option>
        </select>
      </template>
    </div>

    <div class="field" v-else>
      <label>自定义 Cron 表达式</label>
      <input v-model="form.cron" placeholder="0 2 * * *  (每天凌晨 2 点)" />
      <div class="tip">5 位标准 cron:分 时 日 月 周。</div>
    </div>

    <div class="cron-preview" :class="{ bad: !cronPreview.ok }">
      <span class="mark">{{ cronPreview.ok ? '✓' : '✗' }}</span>{{ cronPreview.text }}
    </div>


    <label class="chk">
      <input type="checkbox" v-model="form.enabled" />
      <span>启用此定时任务</span>
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
  border-radius:14px; padding:12px 18px; box-shadow:var(--shadow-sm); transition:border-color .15s; }
.card:hover { border-color:var(--primary); }
.card .k { font-size:12px; color:var(--text-muted); margin-bottom:6px; font-weight:550; }
.card .v { font-size:24px; line-height:1.2; font-weight:780; letter-spacing:-.5px; }
.card .v.pass { color:var(--pass-fg); }
.card .v.pri { color:var(--primary); }

.row { display:grid; grid-template-columns:1.5fr 1.4fr 1fr 90px 118px; align-items:center; gap:12px;
  padding:13px 20px; border-bottom:1px solid var(--border); font-size:13px; transition:background .15s; }
.row:last-child { border-bottom:none; }
.row:not(.head):hover { background:var(--surface-2); }
.row.head { padding:10px 20px; font-family:inherit; font-size:12px; font-weight:600;
  line-height:20px; color:var(--text-muted); letter-spacing:0; background:var(--surface-2); }
.row.head > span { font:inherit; color:inherit; letter-spacing:inherit; }
.c-name { display:flex; align-items:center; gap:10px; font-weight:550; }
.c-name .id { color:var(--text-muted); font-family:ui-monospace,Consolas,monospace; font-size:12px;
  background:var(--surface-2); padding:2px 8px; border-radius:6px; flex:none; }
.c-cron { font-family:ui-monospace,Consolas,monospace; font-size:12.5px; color:var(--text-muted); }
.schedule-time-note { margin:0; padding:10px 20px; font-size:12px; line-height:1.6; color:var(--text-muted); }
.cron-rule { min-width:0; font-family:inherit; color:var(--text); }
.cron-rule summary { cursor:pointer; font-size:12.5px; overflow-wrap:anywhere; }
.cron-rule summary:focus-visible { outline:2px solid var(--primary); outline-offset:3px; border-radius:3px; }
.cron-rule code { display:block; margin-top:6px; color:var(--text-muted); font:11.5px/1.5 ui-monospace,Consolas,monospace; overflow-wrap:anywhere; }
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
.field select { width:100%; height:38px; padding:0 10px; font-size:13px; color:var(--text);
  background:var(--surface-2); border:1px solid var(--border); border-radius:8px;
  transition:border-color .15s; font-family:inherit; cursor:pointer; }
.field select:focus { outline:none; border-color:var(--primary); }
.field .tip { font-size:11.5px; color:var(--text-muted); margin-top:6px; }
.time-row { display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
.time-row .seg { width:auto; min-width:72px; height:38px; padding:0 10px; font-size:13px; color:var(--text);
  background:var(--surface-2); border:1px solid var(--border); border-radius:8px;
  transition:border-color .15s; font-family:inherit; cursor:pointer; }
.time-row .seg:focus { outline:none; border-color:var(--primary); }
.time-row .lbl { font-size:13px; color:var(--text-muted); }
.time-row .colon { font-weight:700; color:var(--text-muted); }
.cron-preview { display:flex; align-items:center; gap:8px; font-size:12.5px; margin-bottom:18px;
  padding:9px 12px; border-radius:8px; background:var(--pass-bg); color:var(--pass-fg); font-family:ui-monospace,Consolas,monospace; }
.cron-preview.bad { background:var(--fail-bg); color:var(--fail-fg); }
.cron-preview .mark { font-weight:700; }
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
  .row { grid-template-columns:minmax(0,1fr) auto; gap:8px; padding:12px 14px; }
  .row.head { display:none; }
  .schedule-time-note { padding:10px 14px; }
  .c-name { min-width:0; overflow-wrap:anywhere; }
  .c-cron { display:block; grid-column:1; grid-row:2; }
  .c-status { grid-column:2; grid-row:1; justify-self:end; }
  .c-act { grid-column:2; grid-row:2; }
}
.target-summary{min-width:0;display:flex;flex-direction:column;gap:4px}.target-summary>span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.target-summary small,.sync-warning{display:block;color:var(--text-muted);font-size:11px}.sync-warning{margin-top:4px;color:var(--fail-fg)}.timing-summary{padding:12px;margin-bottom:18px;background:var(--surface-2);border-radius:8px;font-size:13px;line-height:1.7}.timing-summary small{display:block;color:var(--text-muted);font-size:12px}.row{grid-template-columns:minmax(120px,1.2fr) minmax(110px,1fr) minmax(120px,1.3fr) 100px 140px}.icon-btn:disabled{opacity:.45;cursor:default}@media(max-width:900px){.row{grid-template-columns:minmax(0,1fr) auto}.row.head{display:none}.target-summary{display:flex;grid-column:1;grid-row:3}.c-status{grid-column:2;grid-row:1}.c-act{grid-column:2;grid-row:2}.c-cron{grid-column:1;grid-row:2}}
</style>
