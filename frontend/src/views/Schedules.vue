<script setup>
import { ref, reactive, computed, watch, onMounted } from 'vue'
import { listSchedules, createSchedule, updateSchedule, deleteSchedule } from '../api/schedule'
import { listCases } from '../api/case'
import Modal from '../components/Modal.vue'

const items = ref([])
const cases = ref([])
const loading = ref(true)
const error = ref('')

// 从现有用例聚合出所有用过的 tag,给下拉选(避免手敲字符串敲错);编辑时若旧 tag 已不在用例里也补进来
const allTags = computed(() => {
  const set = new Set()
  for (const c of cases.value) for (const t of (c.tags || [])) if (t) set.add(t)
  if (form.tag && !set.has(form.tag)) set.add(form.tag)
  return [...set].sort()
})

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
const form = reactive({ name: '', cron: '', tag: '', enabled: true })

const total = computed(() => items.value.length)
const enabledCount = computed(() => items.value.filter(s => s.enabled).length)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [ss, cs] = await Promise.all([listSchedules(), listCases()])
    items.value = ss
    cases.value = cs
  } catch (e) {
    error.value = e.message || '加载失败'
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editingId.value = null
  form.name = ''
  form.tag = ''
  form.enabled = true
  Object.assign(cronUi, { freq: 'daily', minute: 0, hour: 2, dow: '1', dom: 1 })
  form.cron = builtCron.value
  formErr.value = ''
  showModal.value = true
}

function openEdit(s) {
  editingId.value = s.id
  form.name = s.name
  form.cron = s.cron
  form.tag = s.tag || ''
  form.enabled = s.enabled
  loadCronToUi(s.cron)
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
  if (cronUi.freq === 'custom' && !cronPreview.value.ok) { formErr.value = 'Cron 表达式非法:' + cronPreview.value.text; return }

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
      <div v-for="(s, i) in items" :key="s.id" class="row">
        <span class="c-name"><span class="id">#{{ i + 1 }}</span>{{ s.name }}</span>
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
      <label>执行频率</label>
      <select v-model="cronUi.freq">
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
    <div class="field">
      <label>用例标签筛选 <span class="opt">(可选,不选跑全部用例)</span></label>
      <select v-model="form.tag">
        <option value="">全部用例</option>
        <option v-for="t in allTags" :key="t" :value="t">{{ t }}</option>
      </select>
      <div class="tip">按用例标签圈一批做定时回归;标签来自「用例管理」里给用例打的 tag。</div>
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
  .row { grid-template-columns:1fr 90px 118px; gap:8px; padding:12px 14px; }
  .c-cron { display:none; }
}
</style>
