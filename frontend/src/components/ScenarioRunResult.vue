<script setup>
import { computed } from 'vue'
import AssertionResults from './AssertionResults.vue'

const props = defineProps({ results: { type: Array, default: () => [] } })
const passedCount = computed(() => props.results.filter(result => result.passed).length)
const failedCount = computed(() => props.results.length - passedCount.value)
const overallPassed = computed(() => props.results.length > 0 && failedCount.value === 0)

function caseName(result) {
  return result.case_name?.trim() || (result.case_id != null ? `用例 #${result.case_id}` : '名称不可用')
}
function statusCode(value) { return value ?? '—' }
function assertionCount(result) { return (result.assertions || []).filter(assertion => assertion.passed).length }
</script>

<template>
  <div class="scenario-run-result">
    <div class="run-verdict" role="status">
      <span class="badge" :class="!results.length ? 'b-skip' : overallPassed ? 'b-pass' : 'b-fail'">
        <span class="dot"></span>{{ !results.length ? '无步骤' : overallPassed ? '通过' : '失败' }}
      </span>
      <span>共 {{ results.length }} 步</span>
      <span>通过 <strong>{{ passedCount }}</strong></span>
      <span :class="{ 'failed-count': failedCount }">失败 <strong>{{ failedCount }}</strong></span>
    </div>

    <div v-if="results.length" class="run-list">
      <div class="run-columns" aria-hidden="true">
        <span>序号</span><span>用例名称</span><span>结果</span><span>期望 / 实际</span><span></span>
      </div>
      <details v-for="(result, index) in results" :key="index" class="run-step" :open="!result.passed">
        <summary class="run-summary">
          <span class="step-index">{{ index + 1 }}</span>
          <span class="step-name" :title="caseName(result)">{{ caseName(result) }}</span>
          <span class="badge step-verdict" :class="result.passed ? 'b-pass' : 'b-fail'">
            <span class="dot"></span>{{ result.passed ? '通过' : '失败' }}
          </span>
          <span class="step-codes" :aria-label="`期望状态 ${statusCode(result.expected_status)}，实际状态 ${result.actual_status ?? '未收到响应'}`">
            <span>{{ statusCode(result.expected_status) }}</span>
            <span class="code-divider">/</span>
            <span :class="{ 'status-mismatch': result.actual_status !== result.expected_status }" :title="result.actual_status == null ? '未收到响应' : undefined">{{ statusCode(result.actual_status) }}</span>
          </span>
          <span class="step-toggle" aria-hidden="true">
            <span class="when-closed">展开</span><span class="when-open">收起</span>
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="m6 4 4 4-4 4" /></svg>
          </span>
        </summary>
        <div class="step-detail">
          <div class="detail-name">{{ caseName(result) }}</div>
          <div v-if="result.error" class="step-error">{{ result.error }}</div>
          <p v-else-if="!result.passed" class="step-error">{{ result.actual_status !== result.expected_status ? '实际状态码不符合预期。' : '断言未通过，请查看下方明细。' }}</p>
          <div v-if="result.assertions?.length" class="step-assertions">
            <div class="assertions-title">断言 · {{ assertionCount(result) }} / {{ result.assertions.length }} 通过</div>
            <AssertionResults :results="result.assertions" />
          </div>
          <p v-else-if="result.passed" class="detail-note">本步骤执行通过，未配置额外断言。</p>
        </div>
      </details>
    </div>
    <p v-else class="empty-result">场景中暂无可执行步骤。</p>
  </div>
</template>

<style scoped>
.run-verdict { display:flex; align-items:center; flex-wrap:wrap; gap:10px 14px; margin-bottom:14px; color:var(--text-muted); font-size:12px; }
.run-verdict strong { font-weight:600; font-variant-numeric:tabular-nums; }
.failed-count { color:var(--fail-fg); }
.run-list { max-height:min(56vh, 480px); overflow:auto; border:1px solid var(--border); border-radius:10px; }
.run-columns, .run-summary { display:grid; grid-template-columns:30px minmax(0, 1fr) 64px 114px 50px; align-items:center; gap:10px; padding:0 12px; }
.run-columns { position:sticky; top:0; z-index:1; min-height:34px; background:var(--surface-2); border-bottom:1px solid var(--border); color:var(--text-muted); font-size:11px; }
.run-step + .run-step { border-top:1px solid var(--border); }
.run-summary { min-height:58px; cursor:pointer; list-style:none; font-size:12px; }
.run-summary::-webkit-details-marker { display:none; }
.run-summary:hover { background:var(--surface-2); }
.run-summary:focus-visible { outline:2px solid var(--primary); outline-offset:-2px; border-radius:6px; }
.step-index { color:var(--text-muted); font-variant-numeric:tabular-nums; }
.step-name { overflow:hidden; white-space:nowrap; text-overflow:ellipsis; font-size:13px; font-weight:600; }
.step-verdict { justify-self:start; padding:4px 9px; }
.step-codes { display:flex; align-items:center; gap:7px; font-family:ui-monospace,Consolas,monospace; font-size:12px; font-variant-numeric:tabular-nums; }
.code-divider { color:var(--text-muted); }
.status-mismatch { color:var(--fail-fg); font-weight:600; }
.step-toggle { display:flex; align-items:center; justify-content:flex-end; gap:3px; color:var(--text-muted); font-size:11px; }
.step-toggle svg { width:13px; height:13px; flex:none; }
.when-open, .run-step[open] .when-closed { display:none; }
.run-step[open] .when-open { display:inline; }
.run-step[open] .step-toggle svg { transform:rotate(90deg); }
.step-detail { padding:0 16px 16px 52px; font-size:12px; }
.detail-name { margin-bottom:10px; color:var(--text); font-weight:600; line-height:1.6; overflow-wrap:anywhere; }
.step-error { margin-bottom:12px; padding:9px 12px; border-radius:6px; background:var(--fail-bg); color:var(--fail-fg); white-space:pre-wrap; overflow-wrap:anywhere; line-height:1.6; }
.step-error:last-child { margin-bottom:0; }
.assertions-title { margin-bottom:8px; color:var(--text-muted); font-weight:600; }
.detail-note, .empty-result { color:var(--text-muted); line-height:1.6; }
.empty-result { padding:24px 12px; text-align:center; border:1px dashed var(--border); border-radius:10px; font-size:12px; }
@media (max-width:600px) {
  .run-columns { display:none; }
  .run-summary { grid-template-columns:22px minmax(0, 1fr) 58px; grid-template-areas:'index name verdict' '. codes toggle'; gap:6px 8px; padding:10px; }
  .step-index { grid-area:index; }
  .step-name { grid-area:name; }
  .step-verdict { grid-area:verdict; justify-self:end; }
  .step-codes { grid-area:codes; }
  .step-codes::before { content:'期望 / 实际'; margin-right:3px; color:var(--text-muted); font:10px -apple-system,"Segoe UI","Microsoft YaHei",sans-serif; }
  .step-toggle { grid-area:toggle; }
  .step-detail { padding:0 12px 14px; }
}
</style>
