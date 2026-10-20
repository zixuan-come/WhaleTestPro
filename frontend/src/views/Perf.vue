<script setup>
import { useFeedback } from '../composables/feedback'
const { showMessage, confirmAction } = useFeedback()
import { ref, reactive, computed, onUnmounted, watch } from 'vue'
import { useAuthStore } from '../stores/auth'
import {
  listPerfTasks, createPerfTask, deletePerfTask, runPerfTask, stopPerfTask,
  updatePerfTask, listPerfRuns, getPerfRun, clearPerfRuns,
} from '../api/perf'
import { listInterfaces } from '../api/interface'
import { listEnvironments } from '../api/environment'
import { listCases } from '../api/case'
import { listScenarios } from '../api/scenario'
import { METHODS, newPerfStep, scenarioSteps, buildPerfPlan } from '../utils/perf-plan'
import { extractRuleRows, PERF_EXTRACT_OPTIONS } from '../utils/extractRules'
import ExtractRulesEditor from '../components/ExtractRulesEditor.vue'
import AssertionEditor from '../components/AssertionEditor.vue'
import { assertionRows } from '../utils/assertionRules'
import { grafanaUrl } from '../utils/serviceUrls'
import EnvironmentSelect from '../components/EnvironmentSelect.vue'
import Modal from '../components/Modal.vue'

const items = ref([])
const grafanaHref = grafanaUrl()
const auth = useAuthStore()
const pollError = ref('')
const stoppingId = ref(null)
let pageVersion = 0, refreshSerial = 0, refreshPending = null
const interfaces = ref([])
const envs = ref([])
const cases = ref([])
const scenarios = ref([])
const steps = ref([newPerfStep()])
const loading = ref(true)
const error = ref('')

const showModal = ref(false)
const showDetail = ref(false)
const detailTask = ref(null)
const detailFollowsLatest = ref(true)
const detailExecutionId = ref(null)
let detailVersion = 0, historyVersion = 0
const editingId = ref(null)
const showHistory = ref(false)
const historyTask = ref(null)
const historyRows = ref([])
const historyTotal = ref(0)
const historyOffset = ref(0)
const historyLoading = ref(false)
const historyError = ref('')
const selectedRuns = ref([])
const clearingRuns = ref(false)
const HISTORY_PAGE_SIZE = 10
const transactionStats = computed(() => {
  const s = detailTask.value?.iteration_stats
  if (typeof s?.iterations !== 'number' || typeof s?.failures !== 'number') return null
  const elapsed = s.elapsed_seconds
  return { count: s.iterations, failures: s.failures,
    average: s.avg_tps ?? s.iteration_rps,
    success: s.success_tps ?? (elapsed > 0 ? (s.iterations - s.failures) / elapsed : null),
    failRatio: s.fail_ratio ?? (s.iterations > 0 ? s.failures / s.iterations : 0),
    current: detailTask.value.history_samples?.at(-1)?.tps,
  }
})
const errorsExpanded = ref(false)
watch(() => Boolean(detailTask.value?.error_summary?.length), (hasErrors) => {
  if (hasErrors) errorsExpanded.value = true
})
const saving = ref(false)
const formErr = ref('')
const runningId = ref(null)      // 正在触发运行的任务 id
const form = reactive({ name: '', interface_id: '', scenario_id: '', env_id: '', target_host: '', users: 10, spawn_rate: 2, duration: 30,
  mode: 'single', variables: '{}', datasets: '[]', stop_on_failure: true, timeout_seconds: 30, wait_seconds: 1 })

const total = computed(() => items.value.length)
const runningCount = computed(() => items.value.filter(t => ['queued', 'running'].includes(t.status)).length)
const detailLive = computed(() => ['queued', 'running'].includes(detailTask.value?.status))
const latestSample = computed(() => detailTask.value?.history_samples?.at(-1))
const requestTotals = computed(() => (detailTask.value?.request_stats || []).reduce((total, row) => ({
  requests: total.requests + (row.num_requests || 0), failures: total.failures + (row.num_failures || 0),
}), { requests: 0, failures: 0 }))
function sampleTime(value) { return value ? new Date(value).toLocaleTimeString('zh-CN', { hour12: false }) : '—' }
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
  const maxRpsValue = Math.max(...samples.map(s => Math.max(Number(s.rps) || 0, Number(s.tps) || 0)), 1)
  const maxLatency = Math.max(...samples.map(s => Number(s.avg_response_ms) || 0), 1)
  const toPoints = (key, maxValue) => samples.map((sample, index) => {
    if (key === 'tps' && sample.tps == null) return null
    const x = padX + (index / (samples.length - 1)) * plotW
    const y = padY + plotH - ((Number(sample[key]) || 0) / maxValue) * plotH
    return `${x.toFixed(1)},${y.toFixed(1)}`
  }).filter(Boolean).join(' ')
  return {
    rpsPoints: toPoints('rps', maxRpsValue),
    tpsPoints: samples.some(s => s.tps != null) ? toPoints('tps', maxRpsValue) : null,
    maxTps: Math.max(...samples.map(s => Number(s.tps) || 0)),
    latencyPoints: toPoints('avg_response_ms', maxLatency),
    maxRps: maxRpsValue,
    maxLatency,
    lastElapsed: samples[samples.length - 1].elapsed_s,
  }
})

const STATUS_TEXT = { pending: '待运行', queued: '排队中', running: '运行中', done: '已完成', failed: '失败', cancelled: '已停止' }
function statusText(s) { return STATUS_TEXT[s] || s || '—' }
function statusClass(s) {
  if (s === 'done') return 'b-pass'
  if (s === 'queued' || s === 'running') return 'b-warn'
  if (s === 'failed') return 'b-fail'
  return 'b-skip'
}

function fmtRps(v) { return v == null ? '—' : v.toFixed(1) }
function fmtMs(v) { return v == null ? '—' : Math.round(v) + ' ms' }
function fmtFail(v) { return v == null ? '—' : (v * 100).toFixed(1) + '%' }

async function load() {
  const version = ++pageVersion
  if (!auth.currentProjectId) { loading.value = false; return }
  loading.value = true
  error.value = ''
  try {
    const [tasks, ifs, es, cs, scs] = await Promise.all([listPerfTasks(), listInterfaces(), listEnvironments(), listCases(), listScenarios()])
    if (version !== pageVersion) return
    items.value = tasks
    interfaces.value = ifs
    envs.value = es
    cases.value = cs
    scenarios.value = scs
  } catch (e) {
    if (version === pageVersion) error.value = e.message || '加载失败'
  } finally {
    if (version === pageVersion) loading.value = false
  }
}

function openCreate() {
  editingId.value = null
  form.name = ''
  form.interface_id = ''
  form.env_id = ''
  form.target_host = ''
  form.scenario_id = ''
  form.mode = 'single'
  form.variables = '{}'
  form.datasets = '[]'
  form.stop_on_failure = true
  form.timeout_seconds = 30
  form.wait_seconds = 1
  steps.value = [newPerfStep()]
  form.users = 10
  form.spawn_rate = 2
  form.duration = 30
  formErr.value = ''
  showModal.value = true
}

// Import a snapshot, including method, headers, params and body.
function onPickInterface() {
  const it = interfaces.value.find(i => i.id === form.interface_id)
  if (!it) return
  if (form.mode === 'single') steps.value = [newPerfStep(it)]
  if (!form.name.trim()) form.name = `${it.name} 压测`
}

// 选环境 → 自动带出目标 Host(环境 base_url)
function onPickEnv() {
  const e = envs.value.find(x => x.id === form.env_id)
  if (!e) return
  form.target_host = e.base_url || ''
  form.variables = JSON.stringify(e.variables || {}, null, 2)
}

function setMode() {
  formErr.value = ''
  if (form.mode === 'single' && steps.value.length > 1) {
    form.mode = 'chain'
    formErr.value = '请先删除多余步骤，再切换单接口模式（不会自动丢弃步骤）'
  }
}
function addStep() {
  const it = interfaces.value.find(item => item.id === form.interface_id)
  steps.value.push(newPerfStep(it || {}))
}
function moveStep(index, delta) {
  const target = index + delta
  if (target < 0 || target >= steps.value.length) return
  const [step] = steps.value.splice(index, 1)
  steps.value.splice(target, 0, step)
}
function importScenario() {
  try {
    const sc = scenarios.value.find(item => item.id === form.scenario_id)
    const imported = scenarioSteps(sc, cases.value, interfaces.value)
    steps.value = imported
    if (!form.name.trim()) form.name = `${sc.name} 链路压测`
    formErr.value = ''
  } catch (error) { formErr.value = error.message }
}
function statLabel(task, row) {
  const index = /^step_(\d+)$/.exec(row.name || '')
  const step = index && task.load_config?.steps?.[Number(index[1]) - 1]
  return step ? `${step.name} · ${step.path.split('?')[0]}` : row.name
}

function closeModal() {
  if (saving.value) return
  showModal.value = false
}

async function save() {
  const version = pageVersion
  formErr.value = ''
  if (!form.name.trim()) { formErr.value = '请填写任务名称'; return }
  if (!form.target_host.trim()) { formErr.value = '请填写目标 Host'; return }
  if (!(form.users > 0) || !(form.spawn_rate > 0) || !(form.duration > 0)) {
    formErr.value = '并发数 / 每秒启动 / 持续时长都要大于 0'; return
  }

  saving.value = true
  try {
    const plan = buildPerfPlan(form, steps.value)
    const payload = {
      name: form.name.trim(),
      target_host: form.target_host.trim(),
      target_path: plan.steps[0].path.slice(0, 255),
      load_config: plan,
      users: Number(form.users),
      spawn_rate: Number(form.spawn_rate),
      duration: Number(form.duration),
    }
    if (editingId.value) await updatePerfTask(editingId.value, payload)
    else await createPerfTask(payload)
    if (version !== pageVersion) return
    showModal.value = false
    await load()
  } catch (e) {
    if (version === pageVersion) formErr.value = e.message || '保存失败'
  } finally {
    if (version === pageVersion) saving.value = false
  }
}

async function onRun(task) {
  if (runningId.value != null) return
  const version = pageVersion
  runningId.value = task.id
  try {
    const updated = await runPerfTask(task.id)
    if (version !== pageVersion) return
    // 后端先返回 queued；Worker 真正开始后才会变成 running。
    const i = items.value.findIndex(t => t.id === task.id)
    if (i !== -1 && updated) items.value[i] = updated
    if (updated) openDetail(updated)
    await refresh()
  } catch (e) {
    if (version === pageVersion) showMessage(e.message || '启动失败', 'error')
  } finally {
    if (version === pageVersion) runningId.value = null
  }
}

async function onStop(task) {
  if (stoppingId.value != null) return
  const version = pageVersion
  stoppingId.value = task.id
  try {
    const updated = await stopPerfTask(task.id, task.celery_task_id)
    if (version !== pageVersion) return
    ++refreshSerial
    const i = items.value.findIndex(t => t.id === task.id)
    if (i !== -1 && updated) items.value[i] = updated
    if (detailTask.value?.id === task.id && updated) detailTask.value = updated
  } catch (e) {
    if (version === pageVersion) showMessage(e.message || '停止失败', 'error')
  } finally {
    if (version === pageVersion) stoppingId.value = null
  }
}

function openDetail(task, followsLatest = true) {
  ++detailVersion
  detailFollowsLatest.value = followsLatest
  detailExecutionId.value = task.celery_task_id
  detailTask.value = task
  errorsExpanded.value = Boolean(task.error_summary?.length)
  showDetail.value = true
}

async function openLatestResult(task) {
  if (['queued', 'running'].includes(task.status)) { openDetail(task); return }
  if (!task.latest_run_id) { showMessage('暂无执行记录，请先运行任务', 'info'); return }
  const version = ++detailVersion, page = pageVersion
  try {
    const run = await getPerfRun(task.id, task.latest_run_id)
    if (version === detailVersion && page === pageVersion) openDetail(run.result, false)
  } catch (e) { if (version === detailVersion && page === pageVersion) showMessage(e.message || '读取结果失败', 'error') }
}

function openEdit(task) {
  openCreate()
  editingId.value = task.id
  Object.assign(form, { name: task.name, target_host: task.target_host, users: task.users, spawn_rate: task.spawn_rate, duration: task.duration })
  const plan = task.load_config
  if (plan) {
    Object.assign(form, { mode: plan.mode, variables: JSON.stringify(plan.variables || {}, null, 2), datasets: JSON.stringify(plan.datasets || [], null, 2), stop_on_failure: plan.stop_on_failure, timeout_seconds: plan.timeout_seconds, wait_seconds: plan.wait_seconds })
    steps.value = plan.steps.map(step => ({ ...newPerfStep(), ...step, headers: JSON.stringify(step.headers || {}, null, 2), params: JSON.stringify(step.params || {}, null, 2), body: step.body_type === 'raw' ? step.body : step.body_type === 'none' ? '' : JSON.stringify(step.body, null, 2), expected_status: step.expected_status ?? '', extract_rules: extractRuleRows(step.extract_rules), assertions: assertionRows(step.assertions) }))
  } else steps.value = [{ ...newPerfStep(), name: task.name, path: task.target_path }]
}

function runTime(value) {
  if (!value) return '—'
  return new Date(/[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : value + 'Z').toLocaleString('zh-CN', { hour12: false })
}
async function loadHistory(offset = historyOffset.value) {
  const version = ++historyVersion, page = pageVersion
  historyOffset.value = offset; historyLoading.value = true; historyError.value = ''; selectedRuns.value = []
  try {
    const result = await listPerfRuns(historyTask.value.id, { offset, limit: HISTORY_PAGE_SIZE })
    if (version !== historyVersion || page !== pageVersion) return
    historyRows.value = result.items; historyTotal.value = result.total
    if (!result.items.length && offset > 0) return loadHistory(Math.max(0, offset - HISTORY_PAGE_SIZE))
  } catch (e) { if (version === historyVersion && page === pageVersion) historyError.value = e.message || '历史记录加载失败' }
  finally { if (version === historyVersion && page === pageVersion) historyLoading.value = false }
}
function closeHistory() { ++historyVersion; showHistory.value = false; historyLoading.value = false }
function openHistory(task) { historyTask.value = task; historyRows.value = []; historyTotal.value = 0; showHistory.value = true; loadHistory(0) }
function viewRun(run) { closeHistory(); openDetail(run.result, ['queued', 'running'].includes(run.status)) }
async function clearHistory(ids = null) {
  if (clearingRuns.value) return
  const taskId = historyTask.value.id, page = pageVersion
  const accepted = await confirmAction(`确认清理${ids ? '选中的 ' + ids.length + ' 条' : '全部已结束的'}执行记录？任务配置仍然保留，清理后无法恢复。`)
  if (!accepted || page !== pageVersion || !showHistory.value || historyTask.value.id !== taskId) return
  clearingRuns.value = true
  try {
    const result = await clearPerfRuns(taskId, ids ? { run_ids: ids } : { all_finished: true })
    if (page !== pageVersion) return
    showMessage(`已清理 ${result.deleted} 条执行记录，任务配置已保留`, 'success')
    await refresh()
    if (showHistory.value && historyTask.value.id === taskId) await loadHistory()
  } catch (e) { if (page === pageVersion) showMessage(e.message || '清理失败', 'error') }
  finally { if (page === pageVersion) clearingRuns.value = false }
}

async function onDelete(task) {
  if (!(await confirmAction(`确认删除压测任务「${task.name}」及其全部执行记录？`))) return
  try {
    await deletePerfTask(task.id)
    items.value = items.value.filter(t => t.id !== task.id)
  } catch (e) {
    showMessage(e.message || '删除失败', 'error')
  }
}

// 有任务在 queued/running 时轮询，展示 Worker 实际开始和最终结果。
let pollTimer = null
async function refresh() {
  const version = pageVersion
  if (!auth.currentProjectId || refreshPending === version) return
  refreshPending = version
  const serial = ++refreshSerial
  try {
    const tasks = await listPerfTasks()
    if (version !== pageVersion || serial !== refreshSerial) return
    pollError.value = ''
    items.value = tasks
    if (showDetail.value && detailTask.value && detailFollowsLatest.value) {
      const latest = tasks.find(t => t.id === detailTask.value.id)
      if (latest && latest.celery_task_id === detailExecutionId.value) detailTask.value = latest
    }
  } catch {
    if (version === pageVersion && serial === refreshSerial) pollError.value = '实时数据刷新失败，已保留上次采样，将继续重试。'
  } finally {
    if (refreshPending === version) refreshPending = null
  }
}
function startPoll() { if (!pollTimer) pollTimer = setInterval(refresh, 3000) }
function stopPoll() { if (pollTimer) { clearInterval(pollTimer); pollTimer = null } }
watch(runningCount, (n) => { n > 0 ? startPoll() : stopPoll() })

watch(() => auth.currentProjectId, () => {
  ++pageVersion; ++refreshSerial; refreshPending = null; stopPoll()
  ++detailVersion; closeHistory(); clearingRuns.value = false; editingId.value = null; saving.value = false
  items.value = []; detailTask.value = null; showDetail.value = false
  interfaces.value = []; cases.value = []; scenarios.value = []; envs.value = []
  runningId.value = null; stoppingId.value = null; pollError.value = ''; showModal.value = false
  load()
}, { immediate: true })
onUnmounted(() => { stopPoll(); ++pageVersion; ++refreshSerial })
</script>

<template>
  <div class="cards">
    <div class="card"><div class="k">压测任务</div><div class="v pri">{{ total }}</div></div>
    <div class="card"><div class="k">排队/运行中</div><div class="v warn">{{ runningCount }}</div></div>
    <div class="card"><div class="k">已完成</div><div class="v pass">{{ doneCount }}</div></div>
    <div class="card"><div class="k">峰值 RPS</div><div class="v">{{ maxRps }}</div></div>
  </div>

  <div class="panel">
    <div class="panel-head">
      压测任务
      <div class="head-actions">
        <a class="btn btn-ghost mon" :href="grafanaHref" target="_blank" rel="noopener"
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
          <button v-if="!['queued', 'running'].includes(t.status)" class="btn btn-ghost live-detail-button" :disabled="runningId != null || runningCount > 0" @click="onRun(t)">
            {{ t.status === 'pending' ? '运行' : '再次运行' }}
          </button>
          <button v-if="['queued', 'running'].includes(t.status)" class="icon-btn stop" title="停止" :disabled="stoppingId === t.id" @click="onStop(t)">■</button>
          <button v-if="t.history_count || ['queued','running'].includes(t.status)" class="btn btn-ghost live-detail-button" @click="openLatestResult(t)">{{ ['queued','running'].includes(t.status) ? '实时结果' : '查看结果' }}</button>
          <button class="btn btn-ghost live-detail-button" @click="openHistory(t)">历史记录</button>
          <button class="icon-btn" title="修改配置" aria-label="修改配置" :disabled="['queued','running'].includes(t.status)" @click="openEdit(t)"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m16 3 5 5-12 12-6 1 1-6Z" /></svg></button>
          <button class="icon-btn del" title="删除" :disabled="['queued', 'running'].includes(t.status)" @click="onDelete(t)">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14" /></svg>
          </button>
        </span>
      </div>
    </template>
  </div>

<Modal v-if="showDetail" :title="detailLive ? '压测实时结果' : '压测结果详情'" :max-width="920" hide-scrollbar @close="showDetail = false">
    <div v-if="detailTask" class="perf-detail">
      <div class="detail-head">
        <div class="detail-heading">
          <strong>{{ detailTask.name }}</strong>
          <div class="detail-meta"><span>{{ detailTask.load_config?.mode === 'chain' ? '有序链路' : '单接口' }}</span><span>并发 {{ detailTask.users ?? '—' }}</span><span>持续 {{ detailTask.duration ?? '—' }} 秒</span></div>
          <small>{{ detailTask.target_host }}{{ detailTask.target_path }}</small>
        </div>
        <span class="badge" :class="statusClass(detailTask.status)"><span class="dot"></span>{{ statusText(detailTask.status) }}</span>
        <div class="live-status" role="status"><span>{{ detailLive ? '每 3 秒自动刷新' : '已保留最后采样与累计统计' }}</span><span>{{ latestSample ? '最后采样 ' + sampleTime(latestSample.sampled_at) + ' · 已运行 ' + Math.round(latestSample.elapsed_s) + ' 秒' : '等待首批采样' }}</span></div>
      </div>
      <div v-if="detailTask.failure_reason" class="form-err">{{ detailTask.failure_reason }}</div>
      <div v-if="pollError" class="form-err" role="alert">{{ pollError }} <button class="btn btn-ghost" @click="refresh">重试</button></div>
      <section class="detail-section" aria-label="请求统计概览">
        <div class="detail-metrics"><div><span>RPS</span><strong>{{ fmtRps(detailTask.rps) }}</strong></div><div><span>平均耗时</span><strong>{{ fmtMs(detailTask.avg_response_ms) }}</strong></div><div><span>P95</span><strong>{{ fmtMs(detailTask.p95_response_ms) }}</strong></div><div><span>P99</span><strong>{{ fmtMs(detailTask.p99_response_ms) }}</strong></div><div><span>失败率</span><strong>{{ fmtFail(detailTask.fail_ratio) }}</strong></div></div>
        <div class="live-counts"><span>累计请求 <strong>{{ requestTotals.requests }}</strong></span><span>失败请求 <strong :class="{ bad: requestTotals.failures > 0 }">{{ requestTotals.failures }}</strong></span><span v-if="detailLive">当前用户 <strong>{{ latestSample?.users ?? '—' }}</strong></span></div>
      </section>
      <section v-if="transactionStats" class="detail-section transaction-section">
        <div class="detail-title">事务统计 · TPS</div>
        <div class="detail-metrics transaction-metrics"><div><span>平均 TPS</span><strong>{{ fmtRps(transactionStats.average) }}</strong></div><div><span>成功 TPS</span><strong>{{ fmtRps(transactionStats.success) }}</strong></div><div><span>最近区间 TPS</span><strong>{{ fmtRps(transactionStats.current) }}</strong></div><div><span>事务失败率</span><strong>{{ fmtFail(transactionStats.failRatio) }}</strong></div></div>
        <div class="live-counts"><span>完成事务 <strong>{{ transactionStats.count ?? '—' }}</strong></span><span>失败事务 <strong>{{ transactionStats.failures ?? '—' }}</strong></span><span>整轮平均 <strong>{{ fmtMs(detailTask.iteration_stats.avg_duration_ms) }}</strong></span></div>
        <p class="detail-note">{{ detailTask.load_config?.mode === 'chain' ? '整条链路执行一轮计为一个事务' : '单接口执行一轮计为一个事务' }}；平均 TPS 包含失败事务，成功 TPS 仅计全部检查通过的事务。RPS 按 HTTP 请求统计。</p>
      </section>
      <section class="detail-section">
        <div class="detail-title">接口维度统计</div>
        <div v-if="detailTask.request_stats?.length" class="detail-table detail-table-wide" tabindex="0" aria-label="接口维度统计，窄屏可左右滚动">
          <div class="detail-row detail-row-wide detail-row-head"><span>接口</span><span>请求数</span><span>失败数</span><span>失败率</span><span>RPS</span><span>平均耗时</span><span>P95</span><span>P99</span></div>
          <div v-for="row in detailTask.request_stats" :key="row.method + '-' + row.name" class="detail-row detail-row-wide">
            <span class="detail-interface"><span class="method-tag">{{ row.method }}</span><span :title="statLabel(detailTask, row)">{{ statLabel(detailTask, row) }}</span></span>
            <span>{{ row.num_requests ?? 0 }}</span><span :class="{ bad: row.num_failures > 0 }">{{ row.num_failures ?? 0 }}</span><span :class="{ bad: row.num_failures > 0 }">{{ fmtFail(row.num_requests ? row.num_failures / row.num_requests : 0) }}</span><span>{{ fmtRps(row.rps) }}</span><span>{{ fmtMs(row.avg_response_ms) }}</span><span>{{ fmtMs(row.p95_response_ms) }}</span><span>{{ fmtMs(row.p99_response_ms) }}</span>
          </div>
        </div>
        <div v-else class="state">暂无按接口统计。</div>
      </section>
      <div class="detail-section"><div class="detail-title">历史趋势</div><div v-if="historyChart" class="history-chart"><div class="history-chart-head"><span>压测趋势</span><small>{{ historyChart.tpsPoints ? 'RPS / TPS 左轴' : 'RPS 左轴' }} · 平均耗时右轴 · 运行至 {{ historyChart.lastElapsed }}s</small></div><svg viewBox="0 0 640 190" role="img" aria-label="压测历史趋势图" preserveAspectRatio="none"><line x1="42" y1="18" x2="42" y2="158" /><line x1="598" y1="18" x2="598" y2="158" /><line x1="42" y1="158" x2="598" y2="158" /><line class="grid-line" x1="42" y1="88" x2="598" y2="88" /><text x="6" y="22">{{ fmtRps(historyChart.maxRps) }}</text><text x="10" y="162">0</text><text x="602" y="22">{{ fmtMs(historyChart.maxLatency) }}</text><text x="612" y="162">0 ms</text><polyline class="trend-rps" :points="historyChart.rpsPoints" /><polyline v-if="historyChart.tpsPoints" class="trend-tps" :points="historyChart.tpsPoints" /><polyline class="trend-latency" :points="historyChart.latencyPoints" /></svg><div class="history-legend"><span><i class="legend-rps"></i>RPS（峰值 {{ fmtRps(historyChart.maxRps) }}）</span><span v-if="historyChart.tpsPoints"><i class="legend-tps"></i>TPS（峰值 {{ fmtRps(historyChart.maxTps) }}）</span><span><i class="legend-latency"></i>平均耗时（峰值 {{ fmtMs(historyChart.maxLatency) }}）</span></div></div><div v-else class="state">等待至少两次采样后显示趋势，运行中自动更新。</div></div>
      <details :key="'config-' + detailTask.id" class="detail-disclosure config-disclosure">
        <summary><span>执行配置</span><small>{{ detailTask.load_config?.steps?.length ? '共 ' + detailTask.load_config.steps.length + ' 个步骤' : '目标接口' }}</small></summary>
        <div class="disclosure-body">
          <ol v-if="detailTask.load_config?.steps?.length" class="plan-summary">
            <li v-for="(step, index) in detailTask.load_config.steps" :key="index"><span class="step-number">{{ String(index + 1).padStart(2, '0') }}</span><div class="step-summary"><strong>{{ step.name || '未命名步骤' }}</strong><div><span class="method-tag">{{ step.method }}</span><code>{{ step.path.split('?')[0] }}</code></div></div></li>
          </ol>
          <div v-else class="legacy-target"><span class="method-tag">{{ detailTask.method || '—' }}</span><code>{{ detailTask.target_path || '/' }}</code></div>
        </div>
      </details>
      <details :key="'samples-' + detailTask.id" class="detail-disclosure samples-disclosure">
        <summary><span>历史采样明细</span><small>{{ detailTask.history_samples?.length || 0 }} 条</small></summary>
        <div class="disclosure-body"><div v-if="detailTask.history_samples?.length" class="history-list"><div v-for="sample in detailTask.history_samples" :key="sample.elapsed_s" class="history-row"><span>{{ sample.elapsed_s }}s</span><span>RPS {{ fmtRps(sample.rps) }}</span><span>平均 {{ fmtMs(sample.avg_response_ms) }}</span><span>P95 {{ fmtMs(sample.p95_response_ms) }}</span><span>失败 {{ fmtFail(sample.fail_ratio) }}</span><span v-if="sample.tps != null">TPS {{ fmtRps(sample.tps) }}</span></div></div><div v-else class="state">暂无历史采样。</div></div>
      </details>
      <details :key="'errors-' + detailTask.id" class="detail-disclosure errors-disclosure" :open="errorsExpanded" @toggle="errorsExpanded = $event.target.open">
        <summary><span>错误分布</span><small :class="{ bad: detailTask.error_summary?.length }">{{ detailTask.error_summary?.length || 0 }} 类</small></summary>
        <div class="disclosure-body"><div v-if="detailTask.error_summary?.length" class="error-list"><div v-for="err in detailTask.error_summary" :key="err.name + err.message" class="error-row"><span>{{ statLabel(detailTask, err) }}</span><strong>{{ err.error_count }}</strong><small>{{ err.message || '未提供错误信息' }}</small></div></div><div v-else class="state">本次压测没有记录错误。</div></div>
      </details>
    </div>
    <template #foot><button v-if="detailLive" class="btn btn-ghost" :disabled="stoppingId === detailTask.id" @click="onStop(detailTask)">{{ stoppingId === detailTask.id ? '停止中…' : '停止压测' }}</button><button class="btn btn-primary" @click="showDetail = false">关闭</button></template>
  </Modal>
  <!-- 新建压测弹层 -->
  <Modal v-if="showHistory" :title="'执行历史 · ' + historyTask.name" :max-width="900" hide-scrollbar :busy="clearingRuns" @close="closeHistory">
    <div class="perf-history">
      <div class="history-toolbar"><span>共 {{ historyTotal }} 条记录 · 清理后保留任务配置</span><button class="btn btn-ghost" :disabled="clearingRuns || historyLoading || !historyTotal" @click="clearHistory()">清理已结束记录</button></div>
      <div v-if="historyError" class="form-err" role="alert">{{ historyError }} <button class="btn btn-ghost" @click="loadHistory()">重试</button></div>
      <div v-else-if="historyLoading" class="state">加载中…</div>
      <div v-else-if="!historyRows.length" class="state">暂无执行记录，运行任务后将在这里保留每轮结果。</div>
      <div v-else class="run-list">
        <div v-for="run in historyRows" :key="run.id" class="run-item">
          <input v-model="selectedRuns" type="checkbox" :value="run.id" :aria-label="'选择执行记录 ' + run.id" :disabled="clearingRuns || ['queued','running'].includes(run.status)" />
          <div class="run-info"><strong>#{{ run.id }} · {{ runTime(run.result.queued_at || run.result.started_at || run.created_at) }}</strong><small>{{ run.result.users }} VU · {{ run.result.duration }} 秒 · RPS {{ fmtRps(run.result.rps) }} · 平均 TPS {{ fmtRps(run.result.iteration_stats?.avg_tps ?? run.result.iteration_stats?.iteration_rps) }}</small></div>
          <span class="badge" :class="statusClass(run.status)"><span class="dot"></span>{{ statusText(run.status) }}</span>
          <div class="run-actions"><button class="btn btn-ghost" @click="viewRun(run)">查看结果</button><button class="btn btn-ghost" :disabled="clearingRuns || ['queued','running'].includes(run.status)" @click="clearHistory([run.id])">清理</button></div>
        </div>
      </div>
      <div v-if="historyTotal > HISTORY_PAGE_SIZE" class="history-pagination"><button class="btn btn-ghost" :disabled="historyLoading || clearingRuns || historyOffset === 0" @click="loadHistory(historyOffset - HISTORY_PAGE_SIZE)">上一页</button><span>{{ Math.floor(historyOffset / HISTORY_PAGE_SIZE) + 1 }} / {{ Math.ceil(historyTotal / HISTORY_PAGE_SIZE) }}</span><button class="btn btn-ghost" :disabled="historyLoading || clearingRuns || historyOffset + HISTORY_PAGE_SIZE >= historyTotal" @click="loadHistory(historyOffset + HISTORY_PAGE_SIZE)">下一页</button></div>
    </div>
    <template #foot><span class="history-selected">已选 {{ selectedRuns.length }} 条</span><button class="btn btn-ghost" :disabled="!selectedRuns.length || clearingRuns || historyLoading" @click="clearHistory([...selectedRuns])">清理选中</button><button class="btn btn-primary" :disabled="clearingRuns" @click="closeHistory">关闭</button></template>
  </Modal>
  <Modal v-if="showModal" :title="editingId ? '修改压测配置' : '新建压测任务'" :max-width="820" :busy="saving" @close="closeModal">
    <div class="field">
      <label>任务名称</label>
      <input v-model="form.name" placeholder="如:下单接口 200 并发" />
    </div>
    <div class="grid2 pick">
      <div class="field">
        <label>从接口导入 <span class="opt">(方法、请求头、参数、请求体快照)</span></label>
        <select v-model.number="form.interface_id" @change="onPickInterface">
          <option value="">— 手动配置 —</option>
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
        <label>压测模式</label>
        <select v-model="form.mode" aria-label="压测模式" @change="setMode"><option value="single">单接口</option><option value="chain">有序链路</option></select>
      </div>
    </div>
    <div v-if="form.mode === 'chain'" class="pick grid2">
      <div class="field"><label>导入已有 HTTP 场景</label><select v-model.number="form.scenario_id" aria-label="场景"><option value="">— 选择场景 —</option><option v-for="sc in scenarios" :key="sc.id" :value="sc.id">{{ sc.name }} · {{ (sc.steps || sc.case_ids || []).length }} 步</option></select></div>
      <div class="step-actions"><button class="btn btn-ghost" :disabled="!form.scenario_id" @click="importScenario">导入场景快照</button><button class="btn btn-ghost" :disabled="steps.length >= 100" @click="addStep">添加接口步骤</button></div>
    </div>
    <div v-for="(step, index) in steps" :key="index" class="perf-step">
      <div class="step-head"><strong>步骤 {{ index + 1 }} · {{ step.name }}</strong><div v-if="form.mode === 'chain'" class="step-actions"><button class="btn btn-ghost btn-sm" :disabled="index === 0" :aria-label="`步骤 ${index + 1} 上移`" @click="moveStep(index, -1)">上移</button><button class="btn btn-ghost btn-sm" :disabled="index === steps.length - 1" :aria-label="`步骤 ${index + 1} 下移`" @click="moveStep(index, 1)">下移</button><button class="btn btn-ghost btn-sm" :disabled="steps.length === 1" :aria-label="`删除步骤 ${index + 1}`" @click="steps.splice(index, 1)">删除</button></div></div>
      <div class="grid3">
        <div class="field"><label>步骤名称</label><input v-model="step.name" :aria-label="`步骤 ${index + 1} 名称`" /></div>
        <div class="field"><label>请求方法</label><select v-model="step.method" :aria-label="`步骤 ${index + 1} 方法`"><option v-for="method in METHODS" :key="method">{{ method }}</option></select></div>
        <div class="field"><label>预期状态码（空为 2xx/3xx）</label><input v-model="step.expected_status" type="number" min="100" max="599" :aria-label="`步骤 ${index + 1} 状态码`" /></div>
      </div>
      <div class="field"><label>相对路径（支持 ${变量名}）</label><input v-model="step.path" :aria-label="`步骤 ${index + 1} 路径`" placeholder="/orders/${order_id}" /></div>
      <div class="grid2">
        <div class="field"><label>Headers · JSON 对象</label><textarea v-model="step.headers" :aria-label="`步骤 ${index + 1} Headers`" rows="3" /></div>
        <div class="field"><label>Query 参数 · JSON 对象</label><textarea v-model="step.params" :aria-label="`步骤 ${index + 1} Query`" rows="3" /></div>
      </div>
      <div class="field"><label>请求体类型</label><select v-model="step.body_type" :aria-label="`步骤 ${index + 1} 请求体类型`"><option value="none">无请求体</option><option value="json">JSON</option><option value="form">表单（urlencoded）</option><option value="raw">原始文本（Content-Type 在 Headers 配置）</option></select></div>
      <div v-if="step.body_type !== 'none'" class="field"><label>请求体</label><textarea v-model="step.body" :aria-label="`步骤 ${index + 1} Body`" rows="4" /></div>
      <details><summary>变量提取与业务断言</summary>
        <div class="field"><label>变量提取</label><ExtractRulesEditor v-model="step.extract_rules" :id-prefix="`perf-extract-${index}`" :disabled="saving" :rules-options="PERF_EXTRACT_OPTIONS" result-placeholder="运行时提取" /></div>
        <div class="field"><label>业务断言</label><AssertionEditor v-model="step.assertions" :id-prefix="`perf-assertion-${index}`" :disabled="saving" :allow-database="false" strict /></div>
      </details>
      <label class="check-option"><input v-model="step.allow_redirects" type="checkbox" />允许重定向（可能访问其他 Host，请确认目标可信）</label>
    </div>
    <details class="pick"><summary>初始变量与数据集</summary><div class="grid2">
      <div class="field"><label>初始变量 · JSON 对象</label><textarea v-model="form.variables" aria-label="初始变量" rows="4" /></div>
      <div class="field"><label>数据集 · JSON 对象数组</label><textarea v-model="form.datasets" aria-label="数据集" rows="4" /></div>
    </div><p class="plan-hint">每个用户每轮独立变量/会话；数据集按轮次循环，不保证账号独占。可用 ${_vu_id} 和 ${_iteration} 生成隔离业务标识。配置可能含凭证，请使用测试账号。</p></details>
    <div class="grid2"><div class="field"><label>请求超时 s</label><input v-model.number="form.timeout_seconds" type="number" min="0.1" max="120" step="0.1" /></div><div class="field"><label>每轮结束等待 s</label><input v-model.number="form.wait_seconds" type="number" min="0" max="60" step="0.1" /></div></div>
    <label class="check-option"><input v-model="form.stop_on_failure" type="checkbox" />步骤失败立即结束本轮（不继续执行依赖步骤）</label>
    <p class="plan-hint">创建仅保存快照，点击运行才发流量。场景导入不支持 SQL、用例级数据集或自动重试；当前不支持文件上传、WebSocket 或 JMeter 插件。</p>
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
      <button class="btn btn-primary" @click="save" :disabled="saving">{{ saving ? '保存中…' : editingId ? '保存配置' : '创建' }}</button>
    </template>
  </Modal>
</template>

<style scoped>
.live-status,.live-counts { display:flex; flex-wrap:wrap; align-items:center; gap:12px; font-size:12px; color:var(--text-muted); }
.live-status { justify-content:space-between; line-height:1.7; }
.live-counts { padding:10px 12px; background:var(--surface-2); border:1px solid var(--border); border-radius:8px; gap:20px; }
.live-counts strong { margin-left:5px; font-size:14px; color:var(--text); font-variant-numeric:tabular-nums; }
.live-detail-button { min-width:44px; height:30px; padding:0 6px; font-size:11px; }
.grafana-help { margin-right:auto; align-self:center; font-size:11px; line-height:1.6; color:var(--text-muted); }
.perf-detail .detail-metrics { grid-template-columns:repeat(5,minmax(0,1fr)); }
@media(max-width:640px) { .perf-detail .detail-metrics { grid-template-columns:repeat(2,minmax(0,1fr)); } .grafana-help { display:none; } .live-counts { gap:12px; } }

.perf-step{padding:16px;border:1px solid var(--border);border-radius:10px;margin-bottom:16px;background:var(--surface-2)}.step-head{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-bottom:16px}.step-actions{display:flex;gap:6px;align-items:center;flex-wrap:wrap}.field textarea{width:100%;padding:10px;border:1px solid var(--border);border-radius:8px;background:var(--surface);color:var(--text);font:12px ui-monospace,Consolas,monospace;resize:vertical}.field textarea:focus{outline:2px solid var(--primary);outline-offset:1px}.check-option{display:flex;gap:8px;align-items:center;font-size:12px;margin-bottom:14px}.plan-hint{font-size:12px;color:var(--text-muted);line-height:1.7}.perf-step summary,.pick summary{cursor:pointer;font-size:12px;font-weight:600;margin-bottom:12px}.iteration-metrics{display:flex;gap:14px;flex-wrap:wrap;padding:12px;background:var(--surface-2);border-radius:8px;font-size:12px}.plan-summary{font:12px ui-monospace,Consolas,monospace;color:var(--text-muted);overflow-wrap:anywhere}.plan-summary li{padding:4px 0}@media(max-width:640px){.step-head{align-items:flex-start;flex-direction:column}}
.history-chart{padding:12px 14px;background:var(--surface-2);border:1px solid var(--border);border-radius:9px}.history-chart-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;color:var(--text-muted);font-size:11.5px}.history-chart-head small{font:11px ui-monospace,Consolas,monospace}.history-chart svg{display:block;width:100%;height:190px;background:linear-gradient(to bottom,transparent 49.5%,var(--border) 50%,transparent 50.5%);border-radius:6px}.history-chart line{stroke:var(--border);stroke-width:1}.history-chart .grid-line{stroke-dasharray:3 4}.history-chart text{fill:var(--text-muted);font:10px ui-monospace,Consolas,monospace}.history-chart polyline{fill:none;stroke-width:3;stroke-linecap:round;stroke-linejoin:round}.history-chart .trend-rps{stroke:var(--primary)}.history-chart .trend-latency{stroke:var(--warn-fg);stroke-dasharray:6 5}.history-legend{display:flex;gap:16px;flex-wrap:wrap;margin-top:8px;color:var(--text-muted);font-size:11px}.history-legend span{display:inline-flex;align-items:center;gap:5px}.history-legend i{display:inline-block;width:18px;height:3px;border-radius:3px}.legend-rps{background:var(--primary)}.legend-latency{background:var(--warn-fg)}.history-list{display:flex;flex-direction:column;gap:5px;max-height:210px;overflow:auto}.history-row{display:grid;grid-template-columns:55px 1fr 1fr 1fr 1fr;gap:8px;padding:8px 10px;background:var(--surface-2);border:1px solid var(--border);border-radius:7px;color:var(--text-muted);font:11.5px ui-monospace,Consolas,monospace}.history-row span:first-child{color:var(--text);font-weight:600}@media (max-width:640px){.history-row{grid-template-columns:55px 1fr 1fr}.history-row span:nth-child(n+4){display:none}}
.icon-btn.detail:hover{color:var(--primary);background:var(--surface-2)}.perf-detail{display:flex;flex-direction:column;gap:16px}.detail-head{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:13px 15px;background:var(--surface-2);border:1px solid var(--border);border-radius:10px}.detail-head strong{display:block;font-size:14px}.detail-head small{display:block;margin-top:4px;color:var(--text-muted);font:11.5px ui-monospace,Consolas,monospace;overflow-wrap:anywhere}.detail-metrics{display:grid;grid-template-columns:repeat(5,1fr);gap:8px}.detail-metrics>div{padding:10px 11px;background:var(--surface-2);border:1px solid var(--border);border-radius:8px}.detail-metrics span{display:block;color:var(--text-muted);font-size:11px}.detail-metrics strong{display:block;margin-top:5px;font:700 15px ui-monospace,Consolas,monospace}.detail-section{display:flex;flex-direction:column;gap:8px}.detail-title{font-size:12px;font-weight:700;color:var(--text-muted)}.detail-table{border:1px solid var(--border);border-radius:8px;overflow:hidden}.detail-row{display:grid;grid-template-columns:2fr .7fr .7fr .8fr .8fr;gap:8px;padding:9px 11px;border-bottom:1px solid var(--border);font-size:12px}.detail-row:last-child{border-bottom:0}.detail-row-wide{grid-template-columns:2fr .7fr .7fr .8fr .7fr .9fr .8fr .8fr;}.detail-table-wide{overflow-x:auto}.detail-table-wide .detail-row{min-width:700px}.detail-row-head{background:var(--surface-2);color:var(--text-muted);font-weight:600}.detail-row span:first-child{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.detail-row .bad{color:var(--fail-fg)}.error-list{display:flex;flex-direction:column;gap:6px}.error-row{display:grid;grid-template-columns:1.2fr 60px 2fr;gap:8px;align-items:center;padding:9px 11px;background:var(--surface-2);border:1px solid var(--border);border-radius:8px;font-size:12px}.error-row strong{color:var(--fail-fg)}.error-row small{color:var(--text-muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}@media (max-width:640px){.detail-metrics{grid-template-columns:repeat(2,1fr)}.error-row{grid-template-columns:1fr 44px}.error-row small{grid-column:1/-1}.detail-row:not(.detail-row-wide){grid-template-columns:1.6fr .6fr .6fr}}
.cards { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:14px; margin-bottom:16px; }
.card { min-width:0; background:var(--surface); border:1px solid var(--border);
  border-radius:12px; padding:12px 18px; box-shadow:var(--shadow-sm); transition:border-color .15s; }
.card:hover { border-color:var(--primary); }
.card .k { font-size:12px; line-height:18px; color:var(--text-muted); margin-bottom:6px; font-weight:550; }
.card .v { font-size:24px; line-height:1.2; font-weight:700; font-variant-numeric:tabular-nums; letter-spacing:-.5px; }
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

/* Result overview and disclosures share the modal content edge. */
.perf-detail { gap:20px; min-width:0; }
.perf-detail .detail-head { display:grid; grid-template-columns:minmax(0,1fr) auto; align-items:start; gap:12px; padding:14px 16px; }
.detail-heading { min-width:0; }
.perf-detail .detail-head strong { font-size:15px; line-height:1.5; overflow-wrap:anywhere; }
.detail-meta { display:flex; flex-wrap:wrap; gap:6px 14px; margin-top:5px; font-size:12px; color:var(--text-muted); }
.perf-detail .detail-head small { line-height:1.6; }
.perf-detail .live-status { grid-column:1/-1; padding-top:10px; border-top:1px solid var(--border); gap:4px 12px; font-size:11px; }
.perf-detail .live-counts { padding:3px 0 0; border:0; background:none; border-radius:0; gap:8px 24px; }
.perf-detail .detail-metrics>div { padding:12px; }
.perf-detail .detail-metrics strong { font-family:ui-monospace,Consolas,monospace; font-size:17px; font-weight:700; font-variant-numeric:tabular-nums; }
.perf-detail .detail-title { font-size:13px; color:var(--text); }
.perf-detail .iteration-metrics { padding:10px 12px; gap:8px 18px; }
.iteration-metrics strong { margin-left:4px; font-variant-numeric:tabular-nums; }
.detail-note { margin:0; font-size:11px; color:var(--text-muted); line-height:1.7; }
.perf-detail .detail-row { align-items:center; padding:11px 12px; font-variant-numeric:tabular-nums; }
.detail-row .detail-interface { display:flex; align-items:center; gap:7px; min-width:0; white-space:normal; }
.detail-row .detail-interface>span:last-child { min-width:0; white-space:normal; overflow-wrap:anywhere; }
.perf-detail .detail-table-wide { scrollbar-width:none; -ms-overflow-style:none; }
.perf-detail .detail-table-wide::-webkit-scrollbar { display:none; }
.perf-detail .detail-table-wide:focus-visible { outline:2px solid var(--primary); outline-offset:2px; }
.method-tag { display:inline-flex; flex-shrink:0; align-items:center; padding:2px 5px; border-radius:4px; background:var(--surface-2); color:var(--primary); font-size:10px; line-height:1.5; font-weight:700; }
.detail-disclosure { border:1px solid var(--border); border-radius:9px; min-width:0; overflow:hidden; }
.detail-disclosure + .detail-disclosure { margin-top:-10px; }
.detail-disclosure summary { display:flex; align-items:center; gap:10px; padding:12px 14px; list-style:none; cursor:pointer; font-size:13px; font-weight:600; line-height:20px; transition:background .15s; }
.detail-disclosure summary::-webkit-details-marker { display:none; }
.detail-disclosure summary::before { content:''; width:6px; height:6px; border-right:1.5px solid var(--text-muted); border-bottom:1.5px solid var(--text-muted); transform:rotate(-45deg); margin-right:2px; flex-shrink:0; }
.detail-disclosure[open]>summary::before { transform:rotate(45deg); }
.detail-disclosure summary:hover { background:var(--surface-2); }
.detail-disclosure summary:focus-visible { outline:2px solid var(--primary); outline-offset:-3px; }
.detail-disclosure summary small { margin-left:auto; font-size:11px; font-weight:400; color:var(--text-muted); }
.disclosure-body { border-top:1px solid var(--border); padding:12px 14px; }
.perf-detail .plan-summary { list-style:none; margin:0; padding:0; font:inherit; color:var(--text); }
.perf-detail .plan-summary li { display:flex; align-items:flex-start; gap:12px; padding:10px 0; }
.perf-detail .plan-summary li + li { border-top:1px solid var(--border); }
.perf-detail .plan-summary li:first-child { padding-top:0; }
.perf-detail .plan-summary li:last-child { padding-bottom:0; }
.step-number { display:grid; place-items:center; width:26px; height:26px; border-radius:6px; background:var(--surface-2); font-size:11px; color:var(--text-muted); flex-shrink:0; font-variant-numeric:tabular-nums; }
.step-summary { min-width:0; font-size:12px; line-height:1.7; }
.step-summary strong { display:block; font-weight:600; overflow-wrap:anywhere; }
.step-summary>div,.legacy-target { display:flex; align-items:baseline; gap:8px; margin-top:4px; }
.step-summary code,.legacy-target code { color:var(--text-muted); font:11px/1.7 ui-monospace,Consolas,monospace; overflow-wrap:anywhere; min-width:0; }
.perf-detail .history-list { max-height:none; overflow:visible; }
.perf-detail .error-row small { white-space:normal; overflow-wrap:anywhere; }
.perf-detail .error-row>span { overflow-wrap:anywhere; min-width:0; }
.perf-detail .bad { color:var(--fail-fg); }
.perf-detail .history-chart-head { flex-wrap:wrap; gap:5px 12px; }
.perf-detail .history-chart-head small { font:inherit; font-size:11px; }
@media(max-width:640px) {
  .perf-detail { gap:16px; }
  .perf-detail .detail-head { padding:12px; }
  .perf-detail .detail-metrics>div { padding:10px; }
  .perf-detail .detail-disclosure + .detail-disclosure { margin-top:-6px; }
  .detail-disclosure summary { padding:11px 12px; }
  .disclosure-body { padding:12px; }
  .perf-detail .history-chart { padding:10px; }
  .perf-detail .history-row { grid-template-columns:48px 1fr 1fr; }
  .perf-detail .history-row span:nth-child(n+4) { display:block; }
}


.perf-detail .transaction-metrics { grid-template-columns:repeat(4,minmax(0,1fr)); }
.history-chart .trend-tps { stroke:var(--pass-fg); stroke-dasharray:3 4; }
.legend-tps { background:var(--pass-fg); }
.row { grid-template-columns:minmax(100px,1.3fr) minmax(80px,1.5fr) 90px 78px 54px 64px 54px 54px 60px 270px; }
.c-act { flex-wrap:wrap; }
.c-name { min-width:0; overflow-wrap:anywhere; }
.perf-history { display:flex; flex-direction:column; gap:14px; }
.history-toolbar,.history-pagination { display:flex; align-items:center; justify-content:space-between; gap:10px; flex-wrap:wrap; font-size:12px; color:var(--text-muted); }
.run-list { border:1px solid var(--border); border-radius:9px; overflow:hidden; }
.run-item { display:grid; grid-template-columns:18px minmax(0,1fr) auto auto; gap:12px; align-items:center; padding:12px; border-bottom:1px solid var(--border); }
.run-item:last-child { border-bottom:0; }
.run-item input { accent-color:var(--primary); cursor:pointer; }
.run-info strong { display:block; font-size:12px; font-weight:600; }
.run-info small { display:block; margin-top:5px; font-size:11px; color:var(--text-muted); line-height:1.6; overflow-wrap:anywhere; }
.run-actions { display:flex; gap:6px; }
.run-actions .btn { padding:5px 8px; font-size:11px; }
.history-selected { margin-right:auto; align-self:center; font-size:12px; color:var(--text-muted); }
@media(max-width:1200px) { .row { grid-template-columns:minmax(90px,1fr) 90px 78px 54px 60px 270px; } .c-target,.c-ms,.c-p95,.c-p99 { display:none; } }
@media(max-width:640px) {
 .row { grid-template-columns:minmax(0,1fr) 78px 60px; gap:8px; }
 .c-act { grid-column:1/-1; justify-content:flex-start; }
 .c-load,.c-fail { display:none; }
 .perf-detail .transaction-metrics { grid-template-columns:repeat(2,minmax(0,1fr)); }
 .run-item { grid-template-columns:18px minmax(0,1fr) auto; gap:8px; }
 .run-actions { grid-column:2/-1; justify-content:flex-end; }
}
</style>

