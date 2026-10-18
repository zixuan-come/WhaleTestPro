<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { listExecutionReports } from '../api/report'
import { useAuthStore } from '../stores/auth'
import { formatShanghaiDateTime } from '../utils/time'
import { preferredReportType, rememberReportType, REPORT_TYPES } from '../utils/reportPreferences'
import ReportExecutionDetail from '../components/ReportExecutionDetail.vue'

const auth = useAuthStore()
const route = useRoute()
const linkedReportId = ref(null)
const reportType = ref('case'), items = ref([]), page = ref(1), pageSize = ref(20)
const totalPages = ref(0), reportTotal = ref(0), passedTotal = ref(0), failedTotal = ref(0), runningTotal = ref(0), passRateTotal = ref(0)
const statusFilter = ref('all'), search = ref(''), dateFrom = ref(''), dateTo = ref('')
const loading = ref(false), error = ref(''), openId = ref(null)
let loadVersion = 0, searchTimer
const projectKey = computed(() => `${auth.username}:${auth.currentProjectId}:${auth.token}`)
const currentLabel = computed(() => REPORT_TYPES.find(type => type.value === reportType.value)?.label || '')
const pageStart = computed(() => reportTotal.value ? (page.value - 1) * pageSize.value + 1 : 0)
const pageEnd = computed(() => Math.min(page.value * pageSize.value, reportTotal.value))
const filtered = computed(() => !!(search.value.trim() || statusFilter.value !== 'all' || dateFrom.value || dateTo.value))
const sourceLabel = value => ({ manual: '手动执行', scheduled: '定时任务' }[value] || '未记录')
function duration(value) { return value == null ? '未记录' : value < 1 ? '< 1 ms' : value < 1000 ? `${value} ms` : `${(value / 1000).toFixed(2)} s` }

async function load(targetPage = 1) {
  clearTimeout(searchTimer)
  const version = ++loadVersion, context = projectKey.value
  if (!auth.token || !auth.currentProjectId) {
    items.value = []; reportTotal.value = passedTotal.value = failedTotal.value = runningTotal.value = passRateTotal.value = 0
    page.value = 1; totalPages.value = 0; loading.value = false; error.value = ''; openId.value = null
    return
  }
  loading.value = true
  error.value = ''
  openId.value = null
  try {
    const data = await listExecutionReports({ kind: reportType.value, page: targetPage, page_size: pageSize.value,
      q: search.value.trim() || undefined, status: statusFilter.value,
      date_from: dateFrom.value || undefined, date_to: dateTo.value || undefined })
    if (version !== loadVersion || context !== projectKey.value) return
    if (!Array.isArray(data?.items)) throw Error('报告数据格式错误')
    items.value = data.items
    page.value = data.page
    totalPages.value = data.total_pages
    reportTotal.value = data.total
    passedTotal.value = data.passed_count
    failedTotal.value = data.failed_count
    runningTotal.value = data.running_count
    passRateTotal.value = data.pass_rate
  } catch (e) {
    if (version === loadVersion && context === projectKey.value) error.value = e.message || '加载报告失败'
  } finally { if (version === loadVersion) loading.value = false }
}
function switchType(type) {
  if (type === reportType.value) return
  linkedReportId.value = null
  reportType.value = type
  rememberReportType(auth.username, auth.currentProjectId, type)
  load(1)
}
function resetFilters() { search.value = ''; statusFilter.value = 'all'; dateFrom.value = ''; dateTo.value = ''; load(1) }
function searchChanged() { clearTimeout(searchTimer); searchTimer = setTimeout(() => load(1), 250) }
function changePage(target) { if (target >= 1 && target <= totalPages.value && target !== page.value) load(target) }
function restore() { linkedReportId.value = null; reportType.value = preferredReportType(auth.username, auth.currentProjectId); resetFilters() }
function initialize() {
  if (['regression', 'suite'].includes(route.query.kind)) {
    reportType.value = route.query.kind
    rememberReportType(auth.username, auth.currentProjectId, route.query.kind)
    linkedReportId.value = /^run-[1-9]\d*$/.test(route.query.report || '') ? route.query.report : null
    resetFilters()
    if (typeof route.query.q === 'string' && route.query.q.trim()) {
      search.value = route.query.q.slice(0, 100); load(1)
    }
  } else restore()
}
function tabKey(event, index) {
  const next = { ArrowLeft: (index + 3) % 4, ArrowRight: (index + 1) % 4, Home: 0, End: 3 }[event.key]
  if (next == null) return
  event.preventDefault()
  const type = REPORT_TYPES[next].value
  switchType(type)
  nextTick(() => document.getElementById(`report-tab-${type}`)?.focus())
}
watch(projectKey, restore)
onMounted(initialize)
onBeforeUnmount(() => { loadVersion++; clearTimeout(searchTimer) })
</script>

<template>
  <div class="report-tabs" role="tablist" aria-label="报告分类">
    <button v-for="(type, index) in REPORT_TYPES" :id="`report-tab-${type.value}`" :key="type.value" type="button" role="tab" :aria-selected="reportType === type.value" :tabindex="reportType === type.value ? 0 : -1" aria-controls="report-panel" :class="{ active: reportType === type.value }" @click="switchType(type.value)" @keydown="tabKey($event, index)">{{ type.label }}</button>
  </div>
  <div class="cards">
    <div class="card"><span>报告总数</span><strong>{{ loading ? '—' : reportTotal }}</strong></div>
    <div class="card"><span>通过</span><strong class="pass">{{ loading ? '—' : passedTotal }}</strong></div>
    <div class="card"><span>失败</span><strong class="fail">{{ loading ? '—' : failedTotal }}</strong></div>
    <div class="card"><span title="通过报告数 ÷ 当前筛选条件下的报告总数">报告通过率</span><strong>{{ loading ? '—' : Math.round(passRateTotal * 100) + '%' }}</strong></div>
  </div>
  <div v-if="linkedReportId && auth.token && auth.currentProjectId" class="panel linked-report">
    <div class="panel-head">本次回归报告<button class="btn btn-ghost" @click="linkedReportId = null">关闭明细</button></div>
    <ReportExecutionDetail :key="`${projectKey}-${linkedReportId}`" :report-id="linkedReportId" />
  </div>
  <div id="report-panel" class="panel" role="tabpanel" :aria-labelledby="`report-tab-${reportType}`">
    <div class="panel-head"><div>{{ currentLabel }}报告 <span class="count">共 {{ loading ? '—' : reportTotal }} 条</span><span v-if="!loading && runningTotal" class="running-count">{{ runningTotal }} 条执行中</span></div><button class="btn btn-ghost" :disabled="loading" @click="load(page)">刷新</button></div>
    <div class="report-filters">
      <input v-model="search" aria-label="搜索报告名称" maxlength="100" placeholder="搜索名称…" @input="searchChanged" />
      <label>状态<select v-model="statusFilter" @change="load(1)"><option value="all">全部</option><option value="passed">通过</option><option value="failed">失败</option></select></label>
      <label>执行日期<input v-model="dateFrom" type="date" aria-label="开始日期" @change="load(1)" /></label>
      <span class="date-divider">至</span><input v-model="dateTo" type="date" aria-label="结束日期" @change="load(1)" />
      <button v-if="filtered" class="btn btn-ghost" @click="resetFilters">重置</button>
    </div>
    <div v-if="!auth.currentProjectId" class="state">请先选择项目。</div>
    <div v-else-if="loading" class="state" role="status">正在加载报告…</div>
    <div v-else-if="error" class="state error" role="alert">{{ error }} <button class="btn btn-ghost" @click="load(1)">重试</button></div>
    <div v-else-if="!items.length" class="state">{{ filtered ? '未找到符合条件的报告。' : `暂无${currentLabel}报告，执行后会在这里显示结果。` }}</div>
    <template v-else>
      <div class="report-row head" aria-hidden="true"><span>结果</span><span>名称</span><span class="duration">耗时</span><span class="source">来源</span><span class="environment">环境</span><span class="time">执行时间</span><span></span></div>
      <template v-for="report in items" :key="report.id">
        <button type="button" class="report-row" :class="{ open: openId === report.id }" :aria-expanded="openId === report.id" @click="openId = openId === report.id ? null : report.id">
          <span><span class="badge" :class="report.passed == null ? 'b-skip' : report.passed ? 'b-pass' : 'b-fail'">{{ report.passed == null ? '执行中' : report.passed ? '通过' : '失败' }}</span></span>
          <span class="report-name" :title="report.name">{{ report.name }}<small v-if="report.historical">历史记录</small></span>
          <span class="duration">{{ duration(report.duration_ms) }}</span><span class="source">{{ sourceLabel(report.trigger_source) }}</span><span class="environment" :title="report.environment_name || '未记录'">{{ report.environment_name || '未记录' }}</span><span class="time">{{ formatShanghaiDateTime(report.created_at) }}</span><span class="chevron" aria-hidden="true">{{ openId === report.id ? '⌃' : '⌄' }}</span>
        </button>
        <ReportExecutionDetail v-if="openId === report.id" :key="`${projectKey}-${report.id}`" :report-id="report.id" />
      </template>
    </template>
    <div v-if="!loading && !error && reportTotal" class="pagination">
      <span>显示 {{ pageStart }}–{{ pageEnd }} 条</span><label>每页<select v-model.number="pageSize" @change="load(1)"><option :value="10">10</option><option :value="20">20</option><option :value="50">50</option><option :value="100">100</option></select></label>
      <button class="btn btn-ghost" :disabled="page <= 1" @click="changePage(page - 1)">上一页</button><span>{{ page }} / {{ totalPages }}</span><button class="btn btn-ghost" :disabled="page >= totalPages" @click="changePage(page + 1)">下一页</button>
    </div>
  </div>
</template>

<style scoped>
.linked-report { margin-bottom:20px; }
.report-tabs { display:flex; gap:4px; margin-bottom:18px; padding:4px; width:fit-content; border:1px solid var(--border); border-radius:8px; background:var(--surface); }
.report-tabs button { padding:8px 16px; border:0; border-radius:5px; background:transparent; color:var(--text-muted); font-family:inherit; font-size:13px; cursor:pointer; }
.report-tabs button.active { color:#fff; background:var(--primary); }
.report-tabs button:focus-visible, .report-row:focus-visible { outline:2px solid var(--primary); outline-offset:-2px; }
.cards { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:14px; margin-bottom:20px; }
.card { padding:16px 18px; background:var(--surface); border:1px solid var(--border); border-radius:12px; }
.card > span { display:block; margin-bottom:8px; color:var(--text-muted); font-size:12px; }
.card strong { font-size:26px; font-weight:700; font-variant-numeric:tabular-nums; }
.card .pass { color:var(--pass-fg); }.card .fail { color:var(--fail-fg); }
.panel-head .count, .running-count { margin-left:10px; color:var(--text-muted); font-size:11px; font-weight:400; }
.report-filters { display:flex; align-items:center; flex-wrap:wrap; gap:10px; padding:12px 18px; border-bottom:1px solid var(--border); }
.report-filters label, .pagination label { display:flex; align-items:center; gap:6px; color:var(--text-muted); font-size:12px; }
input, select { height:32px; min-width:0; border:1px solid var(--border); border-radius:5px; padding:0 9px; background:var(--surface-2); color:var(--text); font-family:inherit; font-size:12px; }
input:focus, select:focus { outline:1px solid var(--primary); }
.report-filters > input:first-child { width:200px; }
.date-divider { color:var(--text-muted); font-size:12px; }
.report-row { display:grid; grid-template-columns:74px minmax(150px,1fr) 80px 74px 110px 150px 20px; align-items:center; gap:10px; width:100%; padding:14px 18px; border:0; border-bottom:1px solid var(--border); background:var(--surface); color:var(--text); text-align:left; font-family:inherit; font-size:12px; cursor:pointer; }
.report-row:not(.head):hover, .report-row.open { background:var(--surface-2); }
.report-row.head { color:var(--text-muted); background:var(--surface-2); font-size:11px; cursor:default; }
.report-name { min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-weight:600; }
.report-name small { margin-left:8px; color:var(--text-muted); font-size:10px; font-weight:400; }
.duration, .source, .environment, .time { min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color:var(--text-muted); font-size:11px; }
.chevron { text-align:right; color:var(--text-muted); }
.state { padding:40px 18px; color:var(--text-muted); font-size:13px; text-align:center; }.state.error { color:var(--fail-fg); }
.pagination { display:flex; flex-wrap:wrap; justify-content:flex-end; align-items:center; gap:12px; padding:14px 18px; color:var(--text-muted); font-size:12px; }
@media (max-width:1100px) { .report-row { grid-template-columns:74px minmax(150px,1fr) 76px 74px 145px 20px; }.environment { display:none; } }
@media (max-width:800px) { .report-row { grid-template-columns:68px minmax(100px,1fr) 80px 20px; }.source,.time { display:none; }.cards { grid-template-columns:repeat(2,minmax(0,1fr)); } }
@media (max-width:560px) { .report-tabs { width:100%; gap:2px; }.report-tabs button { flex:1; min-width:0; padding:8px 5px; font-size:11px; }.report-row { grid-template-columns:64px minmax(80px,1fr) 20px; padding:12px; }.duration { display:none; }.report-filters { padding:12px; gap:8px; }.report-filters > input:first-child { width:100%; }.report-filters input[type=date] { width:125px; }.pagination { justify-content:center; } }
</style>
