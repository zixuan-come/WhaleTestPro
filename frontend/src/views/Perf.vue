<script setup>
import { useFeedback } from '../composables/feedback'
const { showMessage, confirmAction } = useFeedback()
import { ref, reactive, computed, onMounted, onUnmounted, watch } from 'vue'
import {
  listPerfTasks, createPerfTask, deletePerfTask, runPerfTask, stopPerfTask,
} from '../api/perf'
import { listInterfaces } from '../api/interface'
import { listEnvironments } from '../api/environment'
import EnvironmentSelect from '../components/EnvironmentSelect.vue'
import Modal from '../components/Modal.vue'

const items = ref([])
const interfaces = ref([])
const envs = ref([])
const loading = ref(true)
const error = ref('')

const showModal = ref(false)
const showDetail = ref(false)
const detailTask = ref(null)
const saving = ref(false)
const formErr = ref('')
const runningId = ref(null)      // 正在触发运行的任务 id
const form = reactive({ name: '', interface_id: '', env_id: '', target_host: '', target_path: '', users: 10, spawn_rate: 2, duration: 30 })

const total = computed(() => items.value.length)
const runningCount = computed(() => items.value.filter(t => t.status === 'running').length)
const doneCount = computed(() => items.value.filter(t => t.status === 'done').length)
const maxRps = computed(() => {
  const vals = items.value.map(t => t.rps).filter(v => v != null)
  return vals.length ? Math.max(...vals).toFixed(1) : '—'
})

const historyChart = computed(() => {
  const samples = detailTask.value?.history_samples || []
  if (samples.length < 2) return null
  const width = 640
  const height = 190
  const padX = 28
  const padY = 18
  const plotW = width - padX * 2
  const plotH = 140
  const maxRpsValue = Math.max(...samples.map(s => Number(s.rps) || 0), 1)
  const maxLatency = Math.max(...samples.map(s => Number(s.avg_response_ms) || 0), 1)
  const toPoints = (key, maxValue) => samples.map((sample, index) => {
    const x = padX + (index / (samples.length - 1)) * plotW
    const y = padY + plotH - ((Number(sample[key]) || 0) / maxValue) * plotH
    return `${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
  return {
    rpsPoints: toPoints('rps', maxRpsValue),
    latencyPoints: toPoints('avg_response_ms', maxLatency),
    maxRps: maxRpsValue,
    maxLatency,
    lastElapsed: samples[samples.length - 1].elapsed_s,
  }
})

const STATUS_TEXT = { pending: '待运行', running: '运行中', done: '已完成', failed: '失败', cancelled: '已停止' }
function statusText(s) { return STATUS_TEXT[s] || s || '—' }
function statusClass(s) {
  if (s === 'done') return 'b-pass'
  if (s === 'running') return 'b-warn'
  if (s === 'failed') return 'b-fail'
  return 'b-skip'
}

function fmtRps(v) { return v == null ? '—' : v.toFixed(1) }
function fmtMs(v) { return v == null ? '—' : Math.round(v) + ' ms' }
function fmtFail(v) { return v == null ? '—' : (v * 100).toFixed(1) + '%' }

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [tasks, ifs, es] = await Promise.all([listPerfTasks(), listInterfaces(), listEnvironments()])
    items.value = tasks
    interfaces.value = ifs
    envs.value = es
  } catch (e) {
    error.value = e.message || '加载失败'
  } finally {
    loading.value = false
  }
}

function openCreate() {
  form.name = ''
  form.interface_id = ''
  form.env_id = ''
  form.target_host = ''
  form.target_path = ''
  form.users = 10
  form.spawn_rate = 2
  form.duration = 30
  formErr.value = ''
  showModal.value = true
}

// 选接口 → 自动带出目标路径(接口 url 只是路径,host 由环境补)
function onPickInterface() {
  const it = interfaces.value.find(i => i.id === form.interface_id)
  if (!it) return
  form.target_path = it.url || ''
  if (!form.name.trim()) form.name = `${it.name} 压测`
}

// 选环境 → 自动带出目标 Host(环境 base_url)
function onPickEnv() {
  const e = envs.value.find(x => x.id === form.env_id)
  if (!e) return
  form.target_host = e.base_url || ''
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
    showMessage(e.message || '启动失败', 'error')
  } finally {
    runningId.value = null
  }
}

async function onStop(task) {
  try {
    const updated = await stopPerfTask(task.id)
    const i = items.value.findIndex(t => t.id === task.id)
    if (i !== -1 && updated) items.value[i] = updated
  } catch (e) {
    showMessage(e.message || '停止失败', 'error')
  }
}

function openDetail(task) { detailTask.value = task; showDetail.value = true }

async function onDelete(task) {
  if (!(await confirmAction(`确认删除压测任务「${task.name}」?`))) return
  try {
    await deletePerfTask(task.id)
    items.value = items.value.filter(t => t.id !== task.id)
  } catch (e) {
    showMessage(e.message || '删除失败', 'error')
  }
}

// 有任务在 running 时轮询静默刷新,让 running→done + 指标自动更新,不用手动刷新页面
let pollTimer = null
async function refresh() {
  try {
    const tasks = await listPerfTasks()
    items.value = tasks
    if (showDetail.value && detailTask.value) {
      const latest = tasks.find(t => t.id === detailTask.value.id)
      if (latest) detailTask.value = latest
    }
  } catch { /* 轮询失败静默,下轮再试 */ }
}
function startPoll() { if (!pollTimer) pollTimer = setInterval(refresh, 3000) }
function stopPoll() { if (pollTimer) { clearInterval(pollTimer); pollTimer = null } }
watch(runningCount, (n) => { n > 0 ? startPoll() : stopPoll() })

onMounted(load)
onUnmounted(stopPoll)
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
      <div class="head-actions">
        <a class="btn btn-ghost mon" href="http://localhost:8089" target="_blank" rel="noopener"
           title="Locust 实时监控:RPS/响应时间曲线、P50/P95/P99、各请求明细">Locust 实时</a>
        <a class="btn btn-ghost mon" href="http://localhost:3000" target="_blank" rel="noopener"
           title="Grafana 看板:压测指标时序曲线">Grafana</a>
        <button class="btn btn-primary" @click="openCreate">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14" /></svg>
          新建压测
        </button>
      </div>
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
        <span class="c-p95">P95</span>
        <span class="c-p99">P99</span>
        <span class="c-fail">失败率</span>
        <span class="c-act">操作</span>
      </div>
      <div v-for="(t, i) in items" :key="t.id" class="row">
        <span class="c-name"><span class="id">#{{ i + 1 }}</span>{{ t.name }}</span>
        <span class="c-target" :title="t.target_host + t.target_path">{{ t.target_host }}{{ t.target_path }}</span>
        <span class="c-load">{{ t.users }} VU · {{ t.duration }}s</span>
        <span class="c-status"><span class="badge" :class="statusClass(t.status)"><span class="dot"></span>{{ statusText(t.status) }}</span></span>
        <span class="c-rps">{{ fmtRps(t.rps) }}</span>
        <span class="c-ms">{{ fmtMs(t.avg_response_ms) }}</span>
        <span class="c-p95">{{ fmtMs(t.p95_response_ms) }}</span>
        <span class="c-p99">{{ fmtMs(t.p99_response_ms) }}</span>
        <span class="c-fail" :class="{ bad: t.fail_ratio > 0 }">{{ fmtFail(t.fail_ratio) }}</span>
        <span class="c-act">
          <button v-if="t.status !== 'running'" class="icon-btn run" title="运行" :disabled="runningId === t.id" @click="onRun(t)">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 4l14 8-14 8V4Z" /></svg>
          </button>
          <button v-if="t.status === 'running'" class="icon-btn stop" title="停止" @click="onStop(t)">■</button>
          <button class="icon-btn detail" title="查看详情" @click="openDetail(t)">≡</button>
          <button class="icon-btn del" title="删除" @click="onDelete(t)">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14" /></svg>
          </button>
        </span>
      </div>
    </template>
  </div>

<Modal v-if="showDetail" title="压测结果详情" :max-width="760" @close="showDetail = false">
    <div v-if="detailTask" class="perf-detail">
      <div class="detail-head"><div><strong>{{ detailTask.name }}</strong><small>{{ detailTask.target_host }}{{ detailTask.target_path }}</small></div><span class="badge" :class="statusClass(detailTask.status)"><span class="dot"></span>{{ statusText(detailTask.status) }}</span></div>
      <div class="detail-metrics"><div><span>RPS</span><strong>{{ fmtRps(detailTask.rps) }}</strong></div><div><span>平均耗时</span><strong>{{ fmtMs(detailTask.avg_response_ms) }}</strong></div><div><span>P95</span><strong>{{ fmtMs(detailTask.p95_response_ms) }}</strong></div><div><span>P99</span><strong>{{ fmtMs(detailTask.p99_response_ms) }}</strong></div><div><span>失败率</span><strong>{{ fmtFail(detailTask.fail_ratio) }}</strong></div></div>
      <div class="detail-section"><div class="detail-title">接口维度统计</div><div v-if="detailTask.request_stats?.length" class="detail-table detail-table-wide"><div class="detail-row detail-row-head"><span>接口</span><span>请求数</span><span>失败数</span><span>失败率</span><span>RPS</span><span>平均耗时</span><span>P95</span><span>P99</span></div><div v-for="row in detailTask.request_stats" :key="`${row.method}-${row.name}`" class="detail-row detail-row-wide"><span>{{ row.method }} {{ row.name }}</span><span>{{ row.num_requests ?? 0 }}</span><span :class="{ bad: row.num_failures > 0 }">{{ row.num_failures ?? 0 }}</span><span :class="{ bad: row.num_failures > 0 }">{{ fmtFail(row.num_requests ? row.num_failures / row.num_requests : 0) }}</span><span>{{ fmtRps(row.rps) }}</span><span>{{ fmtMs(row.avg_response_ms) }}</span><span>{{ fmtMs(row.p95_response_ms) }}</span><span>{{ fmtMs(row.p99_response_ms) }}</span></div></div><div v-else class="state">暂无按接口统计。</div></div>
      <div class="detail-section"><div class="detail-title">历史趋势</div><div v-if="historyChart" class="history-chart"><div class="history-chart-head"><span>压测趋势</span><small>RPS 左轴 · 平均耗时右轴 · 最近 {{ historyChart.lastElapsed }}s</small></div><svg viewBox="0 0 640 190" role="img" aria-label="压测历史趋势图" preserveAspectRatio="none"><line x1="42" y1="18" x2="42" y2="158" /><line x1="598" y1="18" x2="598" y2="158" /><line x1="42" y1="158" x2="598" y2="158" /><line class="grid-line" x1="42" y1="88" x2="598" y2="88" /><text x="6" y="22">{{ fmtRps(historyChart.maxRps) }}</text><text x="10" y="162">0</text><text x="602" y="22">{{ fmtMs(historyChart.maxLatency) }}</text><text x="612" y="162">0 ms</text><polyline class="trend-rps" :points="historyChart.rpsPoints" /><polyline class="trend-latency" :points="historyChart.latencyPoints" /></svg><div class="history-legend"><span><i class="legend-rps"></i>RPS（峰值 {{ fmtRps(historyChart.maxRps) }}）</span><span><i class="legend-latency"></i>平均耗时（峰值 {{ fmtMs(historyChart.maxLatency) }}）</span></div></div><div v-else class="state">采样点不足，完成一次压测后显示趋势。</div></div><div class="detail-section"><div class="detail-title">历史采样明细</div><div v-if="detailTask.history_samples?.length" class="history-list"><div v-for="sample in detailTask.history_samples" :key="sample.elapsed_s" class="history-row"><span>{{ sample.elapsed_s }}s</span><span>RPS {{ fmtRps(sample.rps) }}</span><span>平均 {{ fmtMs(sample.avg_response_ms) }}</span><span>P95 {{ fmtMs(sample.p95_response_ms) }}</span><span>失败 {{ fmtFail(sample.fail_ratio) }}</span></div></div><div v-else class="state">暂无历史采样。</div></div>
      <div class="detail-section"><div class="detail-title">错误分布</div><div v-if="detailTask.error_summary?.length" class="error-list"><div v-for="err in detailTask.error_summary" :key="err.name + err.message" class="error-row"><span>{{ err.name }}</span><strong>{{ err.error_count }}</strong><small>{{ err.message || '未提供错误信息' }}</small></div></div><div v-else class="state">本次压测没有记录错误。</div></div>
    </div>
    <template #foot><button class="btn btn-primary" @click="showDetail = false">关闭</button></template>
  </Modal>
  <!-- 新建压测弹层 -->
  <Modal v-if="showModal" title="新建压测任务" :busy="saving" @close="closeModal">
    <div class="field">
      <label>任务名称</label>
      <input v-model="form.name" placeholder="如:下单接口 200 并发" />
    </div>
    <div class="grid2 pick">
      <div class="field">
        <label>从接口选择 <span class="opt">(可选,自动填路径)</span></label>
        <select v-model.number="form.interface_id" @change="onPickInterface">
          <option value="">— 手动填写 —</option>
          <option v-for="it in interfaces" :key="it.id" :value="it.id">{{ it.name }} · {{ it.method }} {{ it.url }}</option>
        </select>
      </div>
      <div class="field">
        <label>从环境选择 <span class="opt">(可选,自动填 Host)</span></label>
        <EnvironmentSelect v-model="form.env_id" :environments="envs" placeholder="— 手动填写 —" title="从环境选择" @change="onPickEnv" />
      </div>
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
.history-chart{padding:12px 14px;background:var(--surface-2);border:1px solid var(--border);border-radius:9px}.history-chart-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;color:var(--text-muted);font-size:11.5px}.history-chart-head small{font:11px ui-monospace,Consolas,monospace}.history-chart svg{display:block;width:100%;height:190px;background:linear-gradient(to bottom,transparent 49.5%,var(--border) 50%,transparent 50.5%);border-radius:6px}.history-chart line{stroke:var(--border);stroke-width:1}.history-chart .grid-line{stroke-dasharray:3 4}.history-chart text{fill:var(--text-muted);font:10px ui-monospace,Consolas,monospace}.history-chart polyline{fill:none;stroke-width:3;stroke-linecap:round;stroke-linejoin:round}.history-chart .trend-rps{stroke:var(--primary)}.history-chart .trend-latency{stroke:var(--warn-fg);stroke-dasharray:6 5}.history-legend{display:flex;gap:16px;flex-wrap:wrap;margin-top:8px;color:var(--text-muted);font-size:11px}.history-legend span{display:inline-flex;align-items:center;gap:5px}.history-legend i{display:inline-block;width:18px;height:3px;border-radius:3px}.legend-rps{background:var(--primary)}.legend-latency{background:var(--warn-fg)}.history-list{display:flex;flex-direction:column;gap:5px;max-height:210px;overflow:auto}.history-row{display:grid;grid-template-columns:55px 1fr 1fr 1fr 1fr;gap:8px;padding:8px 10px;background:var(--surface-2);border:1px solid var(--border);border-radius:7px;color:var(--text-muted);font:11.5px ui-monospace,Consolas,monospace}.history-row span:first-child{color:var(--text);font-weight:600}@media (max-width:640px){.history-row{grid-template-columns:55px 1fr 1fr}.history-row span:nth-child(n+4){display:none}}
.icon-btn.detail:hover{color:var(--primary);background:var(--surface-2)}.perf-detail{display:flex;flex-direction:column;gap:16px}.detail-head{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:13px 15px;background:var(--surface-2);border:1px solid var(--border);border-radius:10px}.detail-head strong{display:block;font-size:14px}.detail-head small{display:block;margin-top:4px;color:var(--text-muted);font:11.5px ui-monospace,Consolas,monospace;overflow-wrap:anywhere}.detail-metrics{display:grid;grid-template-columns:repeat(5,1fr);gap:8px}.detail-metrics>div{padding:10px 11px;background:var(--surface-2);border:1px solid var(--border);border-radius:8px}.detail-metrics span{display:block;color:var(--text-muted);font-size:11px}.detail-metrics strong{display:block;margin-top:5px;font:700 15px ui-monospace,Consolas,monospace}.detail-section{display:flex;flex-direction:column;gap:8px}.detail-title{font-size:12px;font-weight:700;color:var(--text-muted)}.detail-table{border:1px solid var(--border);border-radius:8px;overflow:hidden}.detail-row{display:grid;grid-template-columns:2fr .7fr .7fr .8fr .8fr;gap:8px;padding:9px 11px;border-bottom:1px solid var(--border);font-size:12px}.detail-row:last-child{border-bottom:0}.detail-row-wide{grid-template-columns:2fr .7fr .7fr .8fr .7fr .9fr .8fr .8fr;}.detail-table-wide{overflow-x:auto}.detail-table-wide .detail-row{min-width:700px}.detail-row-head{background:var(--surface-2);color:var(--text-muted);font-weight:600}.detail-row span:first-child{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.detail-row .bad{color:var(--fail-fg)}.error-list{display:flex;flex-direction:column;gap:6px}.error-row{display:grid;grid-template-columns:1.2fr 60px 2fr;gap:8px;align-items:center;padding:9px 11px;background:var(--surface-2);border:1px solid var(--border);border-radius:8px;font-size:12px}.error-row strong{color:var(--fail-fg)}.error-row small{color:var(--text-muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}@media (max-width:640px){.detail-metrics{grid-template-columns:repeat(2,1fr)}.error-row{grid-template-columns:1fr 44px}.error-row small{grid-column:1/-1}.detail-row{grid-template-columns:1.6fr .6fr .6fr}}
.cards { display:grid; grid-template-columns:repeat(4,1fr); gap:16px; margin-bottom:24px; }
.card { background:var(--surface); border:1px solid var(--border);
  border-radius:14px; padding:18px 20px; box-shadow:var(--shadow-sm); transition:border-color .15s; }
.card:hover { border-color:var(--primary); }
.card .k { font-size:12px; color:var(--text-muted); margin-bottom:10px; font-weight:550; }
.card .v { font-size:27px; font-weight:780; letter-spacing:-.5px; }
.card .v.pass { color:var(--pass-fg); }
.card .v.warn { color:var(--warn-fg); }
.card .v.pri { color:var(--primary); }

.row { display:grid; grid-template-columns:1.3fr 1.7fr 118px 88px 64px 82px 64px 64px 72px 76px; align-items:center; gap:10px;
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
.c-rps, .c-ms, .c-p95, .c-p99, .c-fail { font-family:ui-monospace,Consolas,monospace; font-size:12.5px; font-weight:600; }
.c-fail.bad { color:var(--fail-fg); }
.c-p95, .c-p99 { color:var(--text-muted); }
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

.head-actions { display:flex; align-items:center; gap:8px; }
.head-actions .mon { text-decoration:none; font-size:12.5px; }

/* ===== 弹层 ===== */
.grid2 { display:grid; grid-template-columns:1fr 1fr; gap:14px; }
.grid3 { display:grid; grid-template-columns:1fr 1fr 1fr; gap:14px; }
.field { margin-bottom:18px; }
.field label { display:block; font-size:12.5px; font-weight:600; margin-bottom:8px; color:var(--text); }
.field input { width:100%; height:38px; padding:0 12px; font-size:13px; color:var(--text);
  background:var(--surface-2); border:1px solid var(--border); border-radius:8px;
  transition:border-color .15s; font-family:inherit; }
.field input:focus { outline:none; border-color:var(--primary); }
.field select { width:100%; height:38px; padding:0 10px; font-size:13px; color:var(--text);
  background:var(--surface-2); border:1px solid var(--border); border-radius:8px;
  transition:border-color .15s; font-family:inherit; cursor:pointer; }
.field select:focus { outline:none; border-color:var(--primary); }
.field label .opt { color:var(--text-muted); font-weight:400; font-size:11.5px; }
.pick { padding:12px 14px; margin-bottom:18px; background:var(--surface-2);
  border:1px dashed var(--border); border-radius:10px; }
.pick .field { margin-bottom:0; }

.form-err { color:var(--fail-fg); font-size:12.5px; background:var(--fail-bg); padding:9px 12px; border-radius:8px; }

/* ===== 响应式 ===== */
@media (max-width:1100px) {
  .cards { grid-template-columns:repeat(2,1fr); }
  .row { grid-template-columns:1.2fr 100px 80px 64px 64px 64px 72px 76px; }
  .c-target, .c-ms, .c-p95, .c-p99 { display:none; }
}
@media (max-width:640px) {
  .cards { grid-template-columns:1fr; gap:12px; }
  .row { grid-template-columns:1fr 72px 64px 76px; gap:8px; padding:12px 14px; }
  .c-load, .c-fail { display:none; }
  .grid2, .grid3 { grid-template-columns:1fr; }
}
</style>

