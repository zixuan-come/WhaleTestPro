<script setup>
import { computed, onMounted, ref } from 'vue'
import { getScenarioReport, listReports, listScenarioReports } from '../api/report'
import { formatShanghaiDateTime } from '../utils/time'

const reportType = ref('scenario')
const items = ref([])
const page = ref(1)
const pageSize = ref(20)
const totalPages = ref(0)
const reportTotal = ref(0)
const passedTotal = ref(0)
const failedTotal = ref(0)
const statusFilter = ref('all')
const search = ref('')
const passRateTotal = ref(0)
const loading = ref(true)
const error = ref('')
const openId = ref(null)
const detailLoadingId = ref(null)
const scenarioDetails = ref({})
const detailErrors = ref({})
let loadVersion = 0

const isScenario = computed(() => reportType.value === 'scenario')
const pageStart = computed(() => reportTotal.value ? (page.value - 1) * pageSize.value + 1 : 0)
const pageEnd = computed(() => Math.min(page.value * pageSize.value, reportTotal.value))
const passRate = computed(() => Math.round(passRateTotal.value * 100))
const filteredItems = computed(() => {
  const q = search.value.trim().toLowerCase()
  return items.value.filter(r => (statusFilter.value === 'all' || (statusFilter.value === 'passed' ? r.passed : !r.passed)) && (!q || String(isScenario.value ? r.scenario_name : (r.case_name || '')).toLowerCase().includes(q)))
})

function fmtDetail(value) {
  if (value == null) return '无'
  try { return JSON.stringify(value, null, 2) } catch { return String(value) }
}

function fmtDuration(value) {
  if (value == null) return '—'
  if (value < 1) return '< 1 ms'
  if (value < 1000) return `${value} ms`
  return `${(value / 1000).toFixed(2)} s`
}

function methodClass(method) {
  return `m-${String(method || '').toLowerCase()}`
}

async function fetchScenarioDetail(report) {
  detailLoadingId.value = report.id
  detailErrors.value = { ...detailErrors.value, [report.id]: '' }
  try {
    const detail = await getScenarioReport(report.id)
    scenarioDetails.value = { ...scenarioDetails.value, [report.id]: detail }
  } catch (e) {
    detailErrors.value = { ...detailErrors.value, [report.id]: e.message || '加载场景报告明细失败' }
  } finally {
    if (detailLoadingId.value === report.id) detailLoadingId.value = null
  }
}

async function toggle(report) {
  if (openId.value === report.id) {
    openId.value = null
    return
  }
  openId.value = report.id
  if (isScenario.value && !scenarioDetails.value[report.id]) await fetchScenarioDetail(report)
}

async function load(targetPage = page.value) {
  const version = ++loadVersion
  loading.value = true
  error.value = ''
  try {
    const request = isScenario.value ? listScenarioReports : listReports
    const data = await request(targetPage, pageSize.value)
    if (version !== loadVersion) return
    items.value = data.items
    page.value = data.page
    totalPages.value = data.total_pages
    reportTotal.value = data.total
    passedTotal.value = data.passed_count
    failedTotal.value = data.failed_count
    passRateTotal.value = data.pass_rate
    openId.value = null
  } catch (e) {
    if (version === loadVersion) error.value = e.message || '加载失败'
  } finally {
    if (version === loadVersion) loading.value = false
  }
}

function switchType(type) {
  if (type === reportType.value) return
  reportType.value = type
  page.value = 1
  load(1)
}

function changePage(targetPage) {
  if (targetPage < 1 || targetPage > totalPages.value || targetPage === page.value) return
  load(targetPage)
}

function changePageSize() {
  page.value = 1
  load(1)
}

onMounted(() => load())
</script>

<template>
  <div class="cards">
    <div class="card"><div class="k">报告总数</div><div class="v pri">{{ reportTotal }}</div></div>
    <div class="card"><div class="k">通过</div><div class="v pass">{{ passedTotal }}</div></div>
    <div class="card"><div class="k">失败</div><div class="v fail">{{ failedTotal }}</div></div>
    <div class="card"><div class="k">通过率</div><div class="v">{{ passRate }}<span class="unit">%</span></div></div>
  </div>

  <div class="panel">
    <div class="panel-head report-head">
      <div class="title-wrap"><span>测试报告</span><span class="count">共 {{ reportTotal }} 条</span></div>
      <div class="tabs" role="tablist" aria-label="报告类型">
        <button type="button" role="tab" :aria-selected="isScenario" :class="{ active: isScenario }" @click="switchType('scenario')">场景报告</button>
        <button type="button" role="tab" :aria-selected="!isScenario" :class="{ active: !isScenario }" @click="switchType('case')">单用例报告</button>
      </div>
    </div>

    <div v-if="loading" class="state">加载中…</div>
    <div v-else-if="error" class="state err">{{ error }}<button class="btn btn-ghost retry" @click="load()">重试</button></div>
    <div v-else-if="!items.length" class="state">
      {{ isScenario ? '暂无场景报告，执行一次场景后这里会出现结果' : '暂无单用例报告，执行一次用例后这里会出现结果' }}
    </div>

    <template v-else>
      <div class="report-filters">
        <div class="filter-tabs"><button :class="{ active: statusFilter === 'all' }" @click="statusFilter = 'all'">全部</button><button :class="{ active: statusFilter === 'passed' }" @click="statusFilter = 'passed'">通过</button><button :class="{ active: statusFilter === 'failed' }" @click="statusFilter = 'failed'">失败</button></div>
        <input v-model="search" class="report-search" :placeholder="isScenario ? '搜索场景…' : '搜索用例…'" />
      </div>
      <div v-if="isScenario" class="row scenario head">
        <span>状态</span><span>场景</span><span>步骤</span><span>耗时</span><span>执行时间</span><span class="c-act">明细</span>
      </div>
      <div v-else class="row single head">
        <span>状态</span><span>用例</span><span>执行时间</span><span class="c-act">明细</span>
      </div>

      <template v-for="(report, index) in filteredItems" :key="report.id">
        <div
          class="row"
          :class="[isScenario ? 'scenario' : 'single', { open: openId === report.id }]"
          role="button"
          tabindex="0"
          :aria-expanded="openId === report.id"
          @click="toggle(report)"
          @keyup.enter="toggle(report)"
        >
          <span class="c-status"><span class="badge" :class="report.passed ? 'b-pass' : 'b-fail'"><span class="dot"></span>{{ report.passed ? '通过' : '失败' }}</span></span>
          <span class="c-name"><span class="id">#{{ pageStart + index }}</span>{{ isScenario ? report.scenario_name : (report.case_name || '用例已删除') }}</span>
          <template v-if="isScenario">
            <span class="c-steps"><strong>{{ report.passed_steps }}</strong> / {{ report.total_steps }} 通过</span>
            <span class="c-duration">{{ fmtDuration(report.duration_ms) }}</span>
          </template>
          <span class="c-time">{{ formatShanghaiDateTime(report.created_at) }}</span>
          <span class="c-act"><svg class="chev" :class="{ up: openId === report.id }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M6 9l6 6 6-6" /></svg></span>
        </div>

        <div v-if="openId === report.id && isScenario" class="detail scenario-detail">
          <div v-if="detailLoadingId === report.id" class="detail-state">正在加载步骤明细…</div>
          <div v-else-if="detailErrors[report.id]" class="detail-state err">
            {{ detailErrors[report.id] }}<button class="btn btn-ghost retry" @click.stop="fetchScenarioDetail(report)">重试</button>
          </div>
          <template v-else-if="scenarioDetails[report.id]">
            <div v-for="step in scenarioDetails[report.id].steps" :key="step.id" class="step">
              <div class="step-head">
                <div class="step-title"><span class="step-number">{{ step.sequence }}</span><span>{{ step.case_name || '用例已删除' }}</span></div>
                <div class="step-meta"><span>{{ fmtDuration(step.duration_ms) }}</span><span class="badge" :class="step.passed ? 'b-pass' : 'b-fail'"><span class="dot"></span>{{ step.passed ? '通过' : '失败' }}</span></div>
              </div>
              <div v-if="step.error" class="step-error">{{ step.error }}</div>

              <div class="step-grid">
                <section class="io-section">
                  <h3>请求</h3>
                  <template v-if="step.request_detail">
                    <div class="request-line"><span class="tag-method" :class="methodClass(step.request_detail.method)">{{ step.request_detail.method }}</span><code>{{ step.request_detail.url }}</code></div>
                    <div class="data-block"><span>Headers</span><pre>{{ fmtDetail(step.request_detail.headers) }}</pre></div>
                    <div class="data-block"><span>Params</span><pre>{{ fmtDetail(step.request_detail.params) }}</pre></div>
                    <div class="data-block"><span>Body</span><pre>{{ fmtDetail(step.request_detail.body) }}</pre></div>
                  </template>
                  <div v-else class="muted">请求未发出</div>
                </section>
                <section class="io-section">
                  <h3>响应</h3>
                  <template v-if="step.response_detail">
                    <div class="response-line"><span>HTTP 状态码</span><code>{{ step.response_detail.status_code }}</code><span v-if="step.response_detail.body_truncated" class="truncated">响应体已截断至 64 KB</span></div>
                    <div class="data-block"><span>Headers</span><pre>{{ fmtDetail(step.response_detail.headers) }}</pre></div>
                    <div class="data-block"><span>Body</span><pre>{{ fmtDetail(step.response_detail.body) }}</pre></div>
                  </template>
                  <div v-else class="muted">无响应</div>
                </section>
              </div>

              <section v-if="step.assertions?.length" class="step-section">
                <h3>断言</h3>
                <div class="assertions">
                  <div v-for="(assertion, assertionIndex) in step.assertions" :key="assertionIndex" class="assertion-row">
                    <span class="badge" :class="assertion.passed ? 'b-pass' : 'b-fail'"><span class="dot"></span>{{ assertion.passed ? 'PASS' : 'FAIL' }}</span>
                    <code>{{ fmtDetail(assertion) }}</code>
                  </div>
                </div>
              </section>
              <section v-if="step.extracted_variables" class="step-section"><h3>提取变量</h3><pre>{{ fmtDetail(step.extracted_variables) }}</pre></section>
            </div>
            <div v-if="!scenarioDetails[report.id].steps.length" class="detail-state">该场景没有执行步骤</div>
          </template>
        </div>
        <div v-else-if="openId === report.id" class="detail single-detail">
          <div class="single-summary"><div><span>执行结果</span><strong :class="report.passed ? 'ok' : 'bad'">{{ report.passed ? '通过' : '失败' }}</strong></div><div><span>执行时间</span><strong>{{ formatShanghaiDateTime(report.created_at) }}</strong></div></div>
          <section v-if="report.detail?.request_detail" class="single-section"><h3>请求</h3><div class="request-line"><span class="tag-method" :class="methodClass(report.detail.request_detail.method)">{{ report.detail.request_detail.method }}</span><code>{{ report.detail.request_detail.url }}</code></div><pre>{{ fmtDetail(report.detail.request_detail) }}</pre></section>
          <section v-if="report.detail?.response_detail" class="single-section"><h3>响应</h3><pre>{{ fmtDetail(report.detail.response_detail) }}</pre></section>
          <section v-if="report.detail?.assertions" class="single-section"><h3>断言</h3><pre>{{ fmtDetail(report.detail.assertions) }}</pre></section>
          <details class="raw-detail"><summary>查看原始数据</summary><pre>{{ fmtDetail(report.detail) }}</pre></details>
        </div>
      </template>
    </template>

    <div v-if="reportTotal" class="pagination">
      <span class="page-summary">显示 {{ pageStart }}-{{ pageEnd }} 条</span>
      <label class="page-size">每页<select v-model.number="pageSize" @change="changePageSize"><option :value="10">10</option><option :value="20">20</option><option :value="50">50</option><option :value="100">100</option></select></label>
      <button class="btn btn-ghost btn-sm" :disabled="loading || page <= 1" @click="changePage(page - 1)">上一页</button>
      <span class="page-number">{{ page }} / {{ totalPages }}</span>
      <button class="btn btn-ghost btn-sm" :disabled="loading || page >= totalPages" @click="changePage(page + 1)">下一页</button>
    </div>
  </div>
</template>

<style scoped>
.report-filters { display:flex; align-items:center; justify-content:space-between; gap:12px; padding:12px 20px; border-bottom:1px solid var(--border); background:var(--surface); }
.filter-tabs { display:flex; gap:4px; }
.filter-tabs button { border:1px solid transparent; background:transparent; color:var(--text-muted); border-radius:6px; padding:6px 12px; font-size:12px; cursor:pointer; }
.filter-tabs button.active { color:var(--primary); background:var(--surface-2); border-color:var(--border); }
.report-search { width:220px; height:32px; padding:0 10px; border:1px solid var(--border); border-radius:7px; background:var(--surface-2); color:var(--text); font:inherit; font-size:12px; }
.report-search:focus { outline:none; border-color:var(--primary); }
.single-summary { display:flex; gap:28px; padding:16px 20px; border-bottom:1px solid var(--border); }
.single-summary div { display:flex; flex-direction:column; gap:5px; font-size:11px; color:var(--text-muted); }
.single-summary strong { font-size:14px; color:var(--text); }
.single-summary strong.ok { color:var(--pass-fg); }
.single-summary strong.bad { color:var(--fail-fg); }
.single-section { padding:16px 20px 0; }
.single-section h3 { margin:0 0 10px; font-size:12px; }
.single-section pre { max-height:220px; overflow:auto; padding:12px; border:1px solid var(--border); border-radius:7px; background:var(--bg); }
.raw-detail { margin:16px 20px; border-top:1px solid var(--border); padding-top:12px; }
.raw-detail summary { cursor:pointer; color:var(--text-muted); font-size:12px; }

.cards { display:grid; grid-template-columns:repeat(4,1fr); gap:16px; margin-bottom:24px; }
.card { background:var(--surface); border:1px solid var(--border); border-radius:14px; padding:18px 20px; box-shadow:var(--shadow-sm); transition:border-color .15s; }
.card:hover { border-color:var(--primary); }
.card .k { font-size:12px; color:var(--text-muted); margin-bottom:10px; font-weight:550; }
.card .v { font-size:27px; font-weight:780; letter-spacing:0; }
.card .v .unit { font-size:16px; font-weight:600; margin-left:2px; color:var(--text-muted); }
.card .v.pass { color:var(--pass-fg); }
.card .v.fail { color:var(--fail-fg); }
.card .v.pri { color:var(--primary); }
.report-head { gap:20px; }
.title-wrap { display:flex; align-items:center; gap:10px; }
.tabs { display:inline-grid; grid-template-columns:repeat(2,1fr); padding:3px; border:1px solid var(--border); border-radius:6px; background:var(--surface-2); }
.tabs button { height:28px; padding:0 14px; border:0; border-radius:4px; color:var(--text-muted); background:transparent; font:inherit; font-size:12px; cursor:pointer; }
.tabs button.active { color:#fff; background:var(--primary); }
.row { display:grid; align-items:center; gap:12px; padding:13px 20px; border-bottom:1px solid var(--border); font-size:13px; cursor:pointer; transition:background .15s; }
.row.scenario { grid-template-columns:96px minmax(180px,1.6fr) 110px 90px minmax(150px,1fr) 50px; }
.row.single { grid-template-columns:96px minmax(180px,1.6fr) minmax(150px,1.4fr) 50px; }
.row:not(.head):hover, .row.open { background:var(--surface-2); }
.row:focus-visible { outline:2px solid var(--primary); outline-offset:-2px; }
.row.head { font-size:11.5px; font-weight:600; color:var(--text-muted); text-transform:uppercase; letter-spacing:0; background:var(--surface-2); cursor:default; }
.c-name { display:flex; align-items:center; gap:10px; min-width:0; font-weight:550; overflow-wrap:anywhere; }
.c-name .id { flex:none; color:var(--text-muted); font-family:ui-monospace,Consolas,monospace; font-size:12px; background:var(--surface-2); padding:2px 8px; border-radius:6px; }
.c-steps, .c-duration, .c-time { color:var(--text-muted); font-family:ui-monospace,Consolas,monospace; font-size:12px; }
.c-steps strong { color:var(--pass-fg); }
.c-act { text-align:right; }
.chev { width:16px; height:16px; color:var(--text-muted); transition:transform .2s; }
.chev.up { transform:rotate(180deg); }
.detail { border-bottom:1px solid var(--border); background:var(--bg); }
.detail-state { padding:24px 20px; text-align:center; color:var(--text-muted); font-size:13px; }
.detail-state.err { color:var(--fail-fg); }
.step { background:var(--surface); border-bottom:1px solid var(--border); }
.step:last-child { border-bottom:0; }
.step-head { display:flex; align-items:center; justify-content:space-between; gap:16px; padding:14px 20px; background:var(--surface-2); border-bottom:1px solid var(--border); }
.step-title, .step-meta { display:flex; align-items:center; gap:10px; }
.step-title { min-width:0; font-size:13px; font-weight:650; overflow-wrap:anywhere; }
.step-number { display:inline-flex; align-items:center; justify-content:center; width:24px; height:24px; flex:none; border-radius:50%; color:#fff; background:var(--primary); font-size:11px; }
.step-meta { color:var(--text-muted); font-size:12px; }
.step-error { margin:16px 20px 0; padding:10px 12px; color:var(--fail-fg); background:var(--fail-bg); border-radius:6px; font-size:12px; overflow-wrap:anywhere; }
.step-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); }
.io-section { min-width:0; padding:18px 20px; }
.io-section + .io-section { border-left:1px solid var(--border); }
.io-section h3, .step-section h3 { margin:0 0 12px; color:var(--text); font-size:12px; font-weight:700; }
.request-line, .response-line { display:flex; align-items:center; gap:9px; min-height:26px; margin-bottom:12px; }
.request-line code { min-width:0; overflow-wrap:anywhere; }
.response-line { color:var(--text-muted); font-size:12px; }
.response-line code { color:var(--text); font-weight:700; }
.truncated { margin-left:auto; color:var(--warn-fg); }
.data-block { margin-top:10px; }
.data-block > span { display:block; margin-bottom:5px; color:var(--text-muted); font-size:11px; }
pre, .assertion-row code { margin:0; font-family:ui-monospace,Consolas,monospace; font-size:11.5px; line-height:1.55; color:var(--text); white-space:pre-wrap; overflow-wrap:anywhere; }
.data-block pre, .step-section pre { max-height:220px; overflow:auto; padding:10px 12px; border:1px solid var(--border); border-radius:6px; background:var(--bg); }
.step-section { padding:0 20px 18px; }
.assertions { border:1px solid var(--border); border-radius:6px; overflow:hidden; }
.assertion-row { display:grid; grid-template-columns:74px minmax(0,1fr); align-items:start; gap:10px; padding:10px 12px; border-bottom:1px solid var(--border); }
.assertion-row:last-child { border-bottom:0; }
.single-detail { padding:0 20px; }
.single-detail > pre { max-height:360px; overflow:auto; padding:16px 0; font-size:12px; }
.muted { color:var(--text-muted); font-size:12px; }
.state { padding:48px 20px; text-align:center; color:var(--text-muted); font-size:13px; }
.state.err { color:var(--fail-fg); }
.retry { margin-left:12px; }
.pagination { display:flex; align-items:center; justify-content:flex-end; gap:12px; padding:14px 20px; border-top:1px solid var(--border); color:var(--text-muted); font-size:12px; }
.page-size { display:flex; align-items:center; gap:6px; }
.page-size select { height:30px; padding:0 8px; color:var(--text); background:var(--surface-2); border:1px solid var(--border); border-radius:6px; font:inherit; }
.page-number { min-width:52px; text-align:center; color:var(--text); font-weight:600; }
@media (max-width:1100px) {
  .cards { grid-template-columns:repeat(2,1fr); }
  .row.scenario { grid-template-columns:90px minmax(160px,1fr) 100px 80px 48px; }
  .row.scenario .c-time, .row.scenario.head > span:nth-child(5) { display:none; }
}
@media (max-width:760px) {
  .report-head { align-items:flex-start; flex-direction:column; }
  .tabs { width:100%; }
  .step-grid { grid-template-columns:1fr; }
  .io-section + .io-section { border-left:0; border-top:1px solid var(--border); }
  .row.scenario { grid-template-columns:82px minmax(120px,1fr) 84px 42px; }
  .row.scenario .c-duration, .row.scenario.head > span:nth-child(4) { display:none; }
}
@media (max-width:560px) {
  .cards { grid-template-columns:1fr; gap:12px; }
  .row.single { grid-template-columns:80px minmax(120px,1fr) 42px; }
  .row.single .c-time, .row.single.head > span:nth-child(3) { display:none; }
  .row { gap:8px; padding:12px 14px; }
  .row.scenario { grid-template-columns:78px minmax(110px,1fr) 42px; }
  .row.scenario .c-steps, .row.scenario.head > span:nth-child(3) { display:none; }
  .step-head { align-items:flex-start; padding:12px 14px; }
  .step-meta { align-items:flex-end; flex-direction:column-reverse; }
  .io-section, .step-section { padding-left:14px; padding-right:14px; }
  .pagination { flex-wrap:wrap; justify-content:center; padding:12px 14px; }
  .page-summary { width:100%; text-align:center; }
}
</style>
