<script setup>
import { computed } from 'vue'

const props = defineProps({ result: { type: Object, required: true } })
const response = computed(() => props.result.response_detail)
const fmt = value => typeof value === 'string' ? value : JSON.stringify(value, null, 2)
const contentType = computed(() => Object.entries(response.value?.headers || {})
  .find(([name]) => name.toLowerCase() === 'content-type')?.[1] || '')
const hasBody = computed(() => response.value && Object.hasOwn(response.value, 'body') && (
  response.value.body != null || (String(contentType.value).includes('json') && response.value.status_code !== 204)
))
</script>

<template>
  <section class="case-response" aria-label="本次用例请求与响应">
    <div class="response-heading">
      <strong>响应体</strong>
      <span v-if="result.duration_ms != null">{{ result.duration_ms }} ms</span>
      <span v-if="contentType" class="content-type">{{ contentType }}</span>
    </div>
    <template v-if="response">
      <p v-if="response.body_truncated" class="response-note">响应体过大，仅展示截取内容。</p>
      <pre v-if="hasBody" class="response-body">{{ fmt(response.body) }}</pre>
      <p v-else class="response-empty">{{ response.body_truncated ? '响应体超过展示上限，未保留可展示内容。' : '响应体为空' }}</p>
      <details class="response-details">
        <summary>响应头 <span>{{ Object.keys(response.headers || {}).length }}</span></summary>
        <pre>{{ fmt(response.headers || {}) }}</pre>
      </details>
    </template>
    <p v-else class="response-empty">{{ result.error ? '本次执行未收到可展示的响应。' : '本次结果未包含响应明细，请更新服务后重新运行用例。' }}</p>
    <details v-if="result.request_detail" class="response-details">
      <summary>实际请求</summary>
      <pre>{{ fmt(result.request_detail) }}</pre>
    </details>
    <p v-if="result.teardown_error" class="cleanup-error">后置处理失败：{{ result.teardown_error }}</p>
  </section>
</template>

<style scoped>
.case-response{min-width:0;margin-top:14px;border:1px solid var(--border);border-radius:9px;overflow:hidden;background:var(--surface)}
.response-heading{display:flex;align-items:center;flex-wrap:wrap;gap:8px 14px;padding:10px 12px;font-size:12px;color:var(--text-muted);border-bottom:1px solid var(--border)}
.response-heading strong{font-size:13px;color:var(--text)}.content-type{margin-left:auto;overflow-wrap:anywhere;min-width:0}
pre{margin:0;max-height:360px;overflow:auto;scrollbar-width:thin;scrollbar-color:var(--border) transparent;padding:12px;background:var(--surface-2);color:var(--text);font:12px/1.65 ui-monospace,Consolas,monospace;white-space:pre-wrap;overflow-wrap:anywhere}
pre::-webkit-scrollbar{width:6px;height:6px}pre::-webkit-scrollbar-thumb{background:var(--border);border-radius:6px}
.response-details{border-top:1px solid var(--border)}summary{display:flex;align-items:center;gap:8px;cursor:pointer;padding:10px 12px;font-size:12px;color:var(--text-muted);list-style:none}summary::-webkit-details-marker{display:none}summary::before{content:'›';font-size:15px;line-height:1;transition:transform .15s}details[open]>summary::before{transform:rotate(90deg)}summary:focus-visible{outline:2px solid var(--primary);outline-offset:-2px}summary span{font-size:11px;background:var(--surface-2);border-radius:8px;padding:1px 6px}
.response-note,.response-empty,.cleanup-error{margin:0;padding:12px;font-size:12px;line-height:1.6;color:var(--text-muted);overflow-wrap:anywhere}.cleanup-error{background:var(--fail-bg);color:var(--fail-fg)}
@media(max-width:640px){.content-type{margin-left:0;flex-basis:100%}pre{max-height:280px}}
</style>
