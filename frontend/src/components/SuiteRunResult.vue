<script setup>
import { computed } from 'vue'

const props = defineProps({ result: { type: Object, required: true } })
const items = computed(() => Array.isArray(props.result.results) ? props.result.results : [])
const verdict = computed(() => !props.result.total ? '无执行项' : props.result.failed ? '存在失败' : '全部通过')
const duration = computed(() => {
  const value = props.result.duration_ms
  if (value == null || !Number.isFinite(Number(value))) return '—'
  return Number(value) < 1000 ? `${value} 毫秒` : `${(Number(value) / 1000).toFixed(2)} 秒`
})
function itemName(item) {
  return item.name?.trim() || `${item.type === 'scenario' ? '场景' : '用例'}${item.id == null ? '（名称未记录）' : ' #' + item.id}`
}
function records(item) {
  if (!item.detail) return []
  return (Array.isArray(item.detail) ? item.detail : [item.detail]).filter(value => value && typeof value === 'object')
}
function recordName(item, record, index) {
  if (item.type === 'scenario') return `${index + 1}. ${record.case_name || (record.case_id == null ? '用例名称未记录' : '用例 #' + record.case_id)}`
  return records(item).length > 1 ? `数据组 ${index + 1}` : '用例执行明细'
}
function reason(record) {
  if (record.error || record.teardown_error) return record.error || record.teardown_error
  if (record.expected_status != null && record.actual_status !== record.expected_status) return `期望状态码 ${record.expected_status}，实际 ${record.actual_status ?? '未收到响应'}`
  if (record.assertions?.some(assertion => !assertion.passed)) return '断言未通过'
  return record.passed ? '' : '执行未通过，未返回具体原因'
}
const pretty = value => JSON.stringify(value, null, 2)
</script>

<template>
  <div class="suite-run-result">
    <div class="suite-result-verdict" role="status"><span class="badge" :class="!result.total ? 'b-skip' : result.failed ? 'b-fail' : 'b-pass'"><span class="dot"></span>{{ verdict }}</span></div>
    <dl class="suite-result-summary">
      <div><dt>套件名称</dt><dd>{{ result.suite_name || '名称未记录' }}</dd></div>
      <div><dt>执行耗时</dt><dd>{{ duration }}</dd></div>
      <div><dt>总数</dt><dd>{{ result.total ?? '—' }} 项</dd></div>
      <div><dt>通过</dt><dd class="pass">{{ result.passed ?? '—' }} 项</dd></div>
      <div><dt>失败</dt><dd :class="{ fail: result.failed > 0 }">{{ result.failed ?? '—' }} 项</dd></div>
      <div><dt>通过率</dt><dd>{{ result.pass_rate == null ? '—' : result.pass_rate + '%' }}</dd></div>
    </dl>
    <p class="suite-count-note">总数按场景和独立用例统计，不包含场景内的步骤数。</p>
    <section class="suite-execution-items" aria-label="套件执行明细">
      <h3>执行明细</h3>
      <details v-for="(item, index) in items" :key="index" class="suite-execution-item" :open="!item.passed">
        <summary>
          <span class="badge" :class="item.passed ? 'b-pass' : 'b-fail'">{{ item.passed ? '通过' : '失败' }}</span>
          <span class="execution-item-title" :title="itemName(item)">{{ itemName(item) }}</span>
          <span class="execution-item-kind">{{ item.type === 'scenario' ? '场景' : '用例' }}</span>
          <span class="execution-toggle"><span class="when-closed">展开</span><span class="when-open">收起</span><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="m6 4 4 4-4 4" /></svg></span>
        </summary>
        <div class="execution-item-body">
          <p class="execution-full-name">{{ itemName(item) }}</p>
          <p v-if="item.error || item.teardown_error" class="execution-error">{{ reason(item) }}</p>
          <details v-for="(record, recordIndex) in records(item)" :key="recordIndex" class="execution-record" :open="!record.passed">
            <summary><span class="record-marker" :class="record.passed ? 'pass' : 'fail'">{{ record.passed ? '通过' : '失败' }}</span><strong>{{ recordName(item, record, recordIndex) }}</strong><span class="record-codes" v-if="record.expected_status != null">期望 {{ record.expected_status }} / 实际 {{ record.actual_status ?? '无响应' }}</span><span class="record-disclosure">明细</span></summary>
            <div class="record-body">
              <p v-if="!record.passed" class="execution-error">{{ reason(record) }}</p>
              <p v-if="record.error && record.teardown_error" class="execution-error">清理失败：{{ record.teardown_error }}</p>
              <div v-if="record.assertions?.length" class="record-assertions"><p>断言 · {{ record.assertions.filter(assertion => assertion.passed).length }} / {{ record.assertions.length }} 通过</p><div v-for="(assertion, assertionIndex) in record.assertions" :key="assertionIndex" class="record-assertion"><span class="badge" :class="assertion.passed ? 'b-pass' : 'b-fail'">{{ assertion.passed ? 'PASS' : 'FAIL' }}</span><pre>{{ pretty(assertion) }}</pre></div></div>
              <p v-else-if="record.passed" class="execution-note">执行通过，未配置额外断言。</p>
            </div>
          </details>
          <p v-if="!records(item).length && !item.error && !item.teardown_error" class="execution-note">{{ item.passed ? '执行通过，未返回更多明细。' : '未返回执行明细，请到测试报告查看。' }}</p>
        </div>
      </details>
      <p v-if="!items.length" class="execution-note">{{ result.total ? '未返回逐项明细，可到测试报告查看。' : '本次没有可执行的场景或用例。' }}</p>
    </section>
  </div>
</template>

<style scoped>
.suite-result-verdict { margin-bottom:16px; }
.suite-result-summary { margin:0; }
.suite-result-summary > div { display:grid;grid-template-columns:88px minmax(0,1fr);gap:16px;padding:9px 0;line-height:1.6;font-size:13px; }
.suite-result-summary dt { color:var(--text-muted); }.suite-result-summary dd { margin:0;color:var(--text);overflow-wrap:anywhere;font-variant-numeric:tabular-nums; }
.suite-result-summary .pass,.pass { color:var(--pass-fg); }.suite-result-summary .fail,.fail { color:var(--fail-fg); }
.suite-count-note { margin:8px 0 20px;font-size:11px;color:var(--text-muted);line-height:1.7; }
.suite-execution-items { border-top:1px solid var(--border);padding-top:16px; }.suite-execution-items h3 { margin:0 0 12px;font-size:13px;font-weight:600; }
.suite-execution-item { border-bottom:1px solid var(--border); }.suite-execution-item:last-child { border-bottom:0; }
.suite-execution-item > summary { display:flex;align-items:center;gap:10px;min-height:48px;cursor:pointer;list-style:none;font-size:12px;border-radius:5px;padding:8px 4px; }.suite-execution-item > summary:hover { background:var(--surface-2); }
summary::-webkit-details-marker { display:none; }summary:focus-visible { outline:2px solid var(--primary);outline-offset:-2px; }
.suite-execution-item .badge { padding:3px 9px;flex:none; }.execution-item-title { flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:600; }
.execution-item-kind { font-size:11px;color:var(--text-muted); }.execution-toggle { display:flex;align-items:center;gap:3px;color:var(--text-muted);font-size:11px; }.execution-toggle svg { width:13px;height:13px; }
.when-open,.suite-execution-item[open] > summary .when-closed { display:none; }.suite-execution-item[open] > summary .when-open { display:inline; }.suite-execution-item[open] > summary .execution-toggle svg { transform:rotate(90deg); }
.execution-item-body { padding:4px 4px 14px; }.execution-full-name { font-size:12px;margin:0 0 10px;font-weight:600;overflow-wrap:anywhere;line-height:1.6; }
.execution-error { padding:9px 10px;background:var(--fail-bg);color:var(--fail-fg);border-radius:6px;font-size:12px;line-height:1.7;white-space:pre-wrap;overflow-wrap:anywhere;margin:0 0 10px; }
.execution-note { font-size:12px;color:var(--text-muted);line-height:1.7;margin:0; }
.execution-record { border:1px solid var(--border);border-radius:6px;margin-top:8px; }.execution-record > summary { display:flex;align-items:center;flex-wrap:wrap;gap:6px 10px;list-style:none;cursor:pointer;padding:9px 10px;font-size:11px; }.execution-record strong { min-width:0;flex:1;overflow-wrap:anywhere;font-weight:500;font-size:12px; }
.record-marker { flex:none; }.record-codes,.record-disclosure { color:var(--text-muted);font-size:11px; }.record-disclosure { margin-left:auto; }
.record-body { padding:0 10px 10px; }.record-assertions > p { font-size:11px;color:var(--text-muted);margin-bottom:8px; }.record-assertion { display:flex;align-items:flex-start;gap:8px;margin-top:8px; }.record-assertion pre { min-width:0;flex:1;margin:0;padding:8px;background:var(--surface-2);border-radius:5px;color:var(--text);font:11px/1.6 ui-monospace,Consolas,monospace;white-space:pre-wrap;overflow-wrap:anywhere; }
@media(max-width:480px) { .suite-result-summary > div { grid-template-columns:72px minmax(0,1fr);gap:10px; }.suite-execution-item > summary { gap:7px; }.execution-item-kind { display:none; }.record-codes { flex-basis:100%; }.execution-record strong { min-width:70px; } }
</style>
