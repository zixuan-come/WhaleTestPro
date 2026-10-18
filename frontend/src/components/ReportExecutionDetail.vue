<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { getExecutionReport } from '../api/report'
import { REPORT_TYPES } from '../utils/reportPreferences'
import ReportStepEvidence from './ReportStepEvidence.vue'

defineOptions({ name: 'ReportExecutionDetail' })
const props = defineProps({ reportId: { type: String, required: true } })
const report = ref(null), loading = ref(true), error = ref(''), expanded = ref(new Set())
let requestVersion = 0
const kindLabel = kind => REPORT_TYPES.find(type => type.value === kind)?.label || '执行项'
const sourceLabel = source => ({ manual: '手动执行', scheduled: '定时任务' }[source] || '未记录')
const steps = computed(() => {
  const detail = report.value?.detail
  if (detail?.steps?.length) return detail.steps
  if (detail?.attempts?.length) return detail.attempts
  if (report.value?.kind === 'case') return Array.isArray(detail?.result) ? detail.result : detail?.result ? [detail.result] : []
  return []
})
const savedItems = computed(() => report.value?.historical && !report.value?.children.length
  ? report.value?.detail?.result?.results || [] : report.value?.detail?.unexecuted_items || [])

async function load() {
  const version = ++requestVersion
  loading.value = true
  error.value = ''
  try {
    const result = await getExecutionReport(props.reportId)
    if (version !== requestVersion) return
    report.value = result
    expanded.value = new Set(result.children.filter(child => child.passed === false).map(child => child.id))
  } catch (e) {
    if (version === requestVersion) error.value = e.message || '报告详情加载失败'
  } finally { if (version === requestVersion) loading.value = false }
}
function toggleChild(id) {
  const next = new Set(expanded.value)
  next.has(id) ? next.delete(id) : next.add(id)
  expanded.value = next
}
watch(() => props.reportId, load, { immediate: true })
onBeforeUnmount(() => requestVersion++)
</script>

<template>
  <div class="execution-detail">
    <div v-if="loading" class="detail-state">正在加载报告明细…</div>
    <div v-else-if="error" class="detail-state error">{{ error }} <button class="btn btn-ghost" @click="load">重试</button></div>
    <template v-else-if="report">
      <div class="detail-meta"><span>环境：{{ report.environment_name || '未记录' }}</span><span>来源：{{ sourceLabel(report.trigger_source) }}</span><span v-if="report.duration_ms != null">耗时：{{ report.duration_ms }} ms</span><span v-if="report.historical">历史记录 · 部分信息未记录</span></div>
      <p v-if="report.detail?.error" class="detail-error">{{ report.detail.error }}</p>
      <div v-if="report.kind === 'suite' || report.kind === 'regression'" class="batch-summary">
        <span>执行项 {{ report.detail?.result?.total ?? report.children.length }}</span>
        <span>通过 {{ report.detail?.result?.passed_count ?? report.detail?.result?.passed ?? 0 }}</span>
        <span>失败 {{ report.detail?.result?.failed_count ?? report.detail?.result?.failed ?? 0 }}</span>
      </div>
      <div v-for="child in report.children" :key="child.id" class="child-report">
        <button class="child-summary" :aria-expanded="expanded.has(child.id)" @click="toggleChild(child.id)">
          <span class="badge" :class="child.passed == null ? 'b-skip' : child.passed ? 'b-pass' : 'b-fail'">{{ child.passed == null ? '执行中' : child.passed ? '通过' : '失败' }}</span>
          <span class="child-kind">{{ kindLabel(child.kind) }}</span><strong>{{ child.name }}</strong><span class="child-toggle">{{ expanded.has(child.id) ? '收起' : '展开' }}</span>
        </button>
        <ReportExecutionDetail v-if="expanded.has(child.id)" :report-id="child.id" />
      </div>
      <ReportStepEvidence v-for="(step, index) in steps" :key="index" :evidence="step" :label="report.kind === 'scenario' ? `${index + 1} · ${step.case_name || '名称未记录'}` : `执行明细 ${index + 1}`" />
      <div v-for="(item, index) in savedItems" :key="index" class="saved-item"><ReportStepEvidence v-for="(step, stepIndex) in (Array.isArray(item.detail) ? item.detail : [item.detail || item])" :key="stepIndex" :evidence="step" :label="item.name || `历史执行项 ${index + 1}`" /></div>
      <p v-if="!report.children.length && !steps.length && !savedItems.length && !report.detail?.error" class="detail-state">{{ report.status === 'running' ? '正在执行，请稍后刷新报告。' : '本次没有执行项或未保存明细。' }}</p>
      <details class="raw-detail"><summary>查看原始结果</summary><pre>{{ JSON.stringify(report.detail, null, 2) }}</pre></details>
    </template>
  </div>
</template>

<style scoped>
.execution-detail { padding:14px 18px; background:var(--bg); }
.detail-meta { display:flex; flex-wrap:wrap; gap:8px 18px; margin-bottom:12px; color:var(--text-muted); font-size:11px; }
.detail-state { padding:16px; text-align:center; color:var(--text-muted); font-size:12px; }
.detail-state.error, .detail-error { color:var(--fail-fg); }
.detail-error { padding:10px; border-radius:6px; background:var(--fail-bg); font-size:12px; }
.batch-summary { display:flex; flex-wrap:wrap; gap:18px; margin-bottom:12px; font-size:12px; }
.child-report { margin-top:8px; border:1px solid var(--border); border-radius:8px; overflow:hidden; }
.child-summary { display:flex; align-items:center; gap:10px; width:100%; min-height:48px; padding:10px 12px; border:0; text-align:left; background:var(--surface); color:var(--text); cursor:pointer; }
.child-summary strong { flex:1; min-width:0; overflow-wrap:anywhere; font-size:12px; }
.child-kind, .child-toggle { color:var(--text-muted); font-size:11px; }
.child-summary:focus-visible { outline:2px solid var(--primary); outline-offset:-2px; }
.saved-item { margin-top:8px; }
.raw-detail { margin-top:14px; border-top:1px solid var(--border); padding-top:10px; }
.raw-detail summary { color:var(--text-muted); font-size:12px; cursor:pointer; }
pre { max-height:320px; overflow:auto; margin:10px 0 0; padding:12px; border-radius:6px; background:var(--surface-2); color:var(--text); font:11.5px/1.6 ui-monospace,Consolas,monospace; white-space:pre-wrap; overflow-wrap:anywhere; }
@media (max-width:600px) { .execution-detail { padding:12px 10px; } .child-kind { display:none; } }
</style>
