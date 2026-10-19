<script setup>
import { computed } from 'vue'
import ExtractedVariables from './ExtractedVariables.vue'
import AssertionResults from './AssertionResults.vue'
const props = defineProps({ evidence: { type: Object, required: true }, label: { type: String, default: '' } })
const assertions = computed(() => Array.isArray(props.evidence.assertions) ? props.evidence.assertions : [])
const fmt = value => JSON.stringify(value, null, 2)
</script>

<template>
  <details class="evidence" :open="evidence.passed === false">
    <summary>
      <span class="badge" :class="evidence.passed ? 'b-pass' : 'b-fail'">{{ evidence.passed ? '通过' : '失败' }}</span>
      <strong>{{ label || evidence.case_name || '执行明细' }}</strong>
      <span v-if="evidence.expected_status != null" class="codes">期望 {{ evidence.expected_status }} / 实际 {{ evidence.actual_status ?? '无响应' }}</span>
      <span class="disclosure">查看明细</span>
    </summary>
    <div class="evidence-body">
      <p v-if="evidence.error || evidence.teardown_error" class="error">{{ evidence.error || evidence.teardown_error }}</p>
      <div class="io-grid">
        <details class="data-section"><summary>请求明细</summary><pre v-if="evidence.request_detail">{{ fmt(evidence.request_detail) }}</pre><p v-else>未记录请求明细</p></details>
        <details class="data-section"><summary>响应明细</summary><pre v-if="evidence.response_detail">{{ fmt(evidence.response_detail) }}</pre><p v-else>未记录响应明细</p></details>
      </div>
      <details v-if="assertions.length" class="data-section" :open="assertions.some(item => !item.passed)">
        <summary>断言 · {{ assertions.filter(item => item.passed).length }} / {{ assertions.length }} 通过</summary>
        <AssertionResults :results="assertions" />
      </details>
      <details v-if="evidence.extracted_variables" class="data-section"><summary>提取变量</summary><ExtractedVariables :variables="evidence.extracted_variables" /></details>
    </div>
  </details>
</template>

<style scoped>
.evidence { border:1px solid var(--border); border-radius:8px; background:var(--surface); overflow:hidden; }
.evidence + .evidence { margin-top:8px; }
.evidence > summary { display:flex; align-items:center; flex-wrap:wrap; gap:8px 12px; min-height:48px; padding:10px 12px; cursor:pointer; list-style:none; }
.evidence > summary::-webkit-details-marker { display:none; }
summary:focus-visible { outline:2px solid var(--primary); outline-offset:-2px; }
summary strong { flex:1; min-width:100px; font-size:12px; overflow-wrap:anywhere; }
.codes, .disclosure { color:var(--text-muted); font-size:11px; }
.disclosure { margin-left:auto; }
.evidence-body { padding:0 12px 12px; }
.error { margin:0 0 10px; padding:10px; border-radius:6px; background:var(--fail-bg); color:var(--fail-fg); font-size:12px; white-space:pre-wrap; overflow-wrap:anywhere; }
.io-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px; }
.data-section { min-width:0; margin-top:8px; border:1px solid var(--border); border-radius:6px; }
.data-section > summary { padding:9px 10px; color:var(--text-muted); font-size:12px; cursor:pointer; }
.data-section p { padding:0 10px 10px; color:var(--text-muted); font-size:12px; }
pre { margin:0; max-height:300px; overflow:auto; padding:10px; background:var(--surface-2); color:var(--text); font:11.5px/1.6 ui-monospace,Consolas,monospace; white-space:pre-wrap; overflow-wrap:anywhere; }
@media (max-width:650px) { .io-grid { grid-template-columns:1fr; } .codes { flex-basis:100%; } }
</style>
