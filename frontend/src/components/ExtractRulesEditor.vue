<script setup>
import { computed, ref } from 'vue'
import { extractRuleRows, serializeExtractRules, formatExtractValue } from '../utils/extractRules'

const props = defineProps({ modelValue: { type: [Array, Object, String], default: () => [] },
  idPrefix: { type: String, required: true }, disabled: Boolean,
  results: { type: Array, default: () => [] }, resultsEnabled: { type: Boolean, default: true },
  resultPlaceholder: { type: String, default: '待验证' }, rulesOptions: { type: Object, default: () => ({}) } })
const emit = defineEmits(['update:modelValue'])
const touched = ref(false)
const rows = computed(() => {
  const saved = extractRuleRows(props.modelValue)
  return saved.length ? saved : [{ name: '', path: '' }]
})
const validation = computed(() => {
  try { serializeExtractRules(props.modelValue, props.rulesOptions); return '' }
  catch (e) { return e.message }
})
function update(index, key, value) {
  const next = rows.value.map(row => ({ ...row }))
  next[index][key] = value
  emit('update:modelValue', next)
}
function add() { emit('update:modelValue', [...rows.value, { name: '', path: '' }]) }
function remove(index) { emit('update:modelValue', rows.value.filter((_, i) => i !== index)) }
function resultFor(row) {
  if (!props.resultsEnabled || validation.value || typeof row.name !== 'string' || typeof row.path !== 'string' || !row.name.trim() || !row.path.trim()) return null
  return props.results.find(item => item.name === row.name.trim() && item.path === row.path.trim()) || null
}
</script>

<template>
  <div class="extract-editor" role="group" aria-label="变量提取规则">
    <div class="extract-head" aria-hidden="true"><span>变量名</span><span>提取表达式</span><span>提取结果</span><span></span></div>
    <div v-for="(row, index) in rows" :key="index" class="extract-row">
      <label class="extract-cell"><span class="mobile-label">变量名</span><input :id="`${idPrefix}-name-${index}`" :value="row.name" :disabled="disabled" :aria-label="`第 ${index + 1} 行变量名`" :aria-describedby="touched && validation ? `${idPrefix}-error` : undefined" placeholder="如 order_id" autocomplete="off" spellcheck="false" @input="update(index, 'name', $event.target.value)" @blur="touched = true" /></label>
      <label class="extract-cell"><span class="mobile-label">提取表达式</span><input :id="`${idPrefix}-path-${index}`" :value="row.path" :disabled="disabled" :aria-label="`第 ${index + 1} 行提取表达式`" placeholder="如 $.data.id" autocomplete="off" spellcheck="false" @input="update(index, 'path', $event.target.value)" @blur="touched = true" /></label>
      <div class="extract-result" aria-live="polite"><span class="mobile-label">提取结果</span><template v-if="resultFor(row)"><code v-if="resultFor(row).passed" class="extract-value">{{ formatExtractValue(resultFor(row).value) }}</code><span v-else class="extract-failure">{{ resultFor(row).error || '未提取到匹配值' }}</span></template><span v-else class="extract-pending">{{ resultPlaceholder }}</span></div>
      <button class="extract-remove" type="button" :disabled="disabled" :aria-label="`删除第 ${index + 1} 条提取规则`" title="删除提取规则" @click="remove(index)"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13M10 10v7m4-7v7" /></svg></button>
    </div>
    <button class="extract-add" type="button" :disabled="disabled" @click="add"><span aria-hidden="true">＋</span> 添加提取规则</button>
    <p v-if="touched && validation" :id="`${idPrefix}-error`" class="extract-error" role="alert">{{ validation }}</p>
    <p class="extract-hint">从响应 JSON 中提取，例如 order_id → $.id；后续请求使用 ${order_id}。</p>
  </div>
</template>

<style scoped>
.extract-editor{min-width:0;font-size:12px;color:var(--text)}
.extract-head,.extract-row{display:grid;grid-template-columns:minmax(110px,.85fr) minmax(140px,1.2fr) minmax(90px,1fr) 30px;align-items:center;gap:10px}
.extract-head{padding:8px 0;color:var(--text-muted);font-size:11.5px;border-bottom:1px solid var(--border)}
.extract-row{padding:8px 0;border-bottom:1px solid var(--border)}
.extract-cell{display:block;min-width:0;margin:0;font-weight:400}
.extract-cell input{display:block;box-sizing:border-box;width:100%;min-width:0;height:34px;padding:0 9px;border:1px solid var(--border);border-radius:6px;background:var(--surface);color:var(--text);font:12px ui-monospace,Consolas,monospace}
.extract-cell input:focus{outline:2px solid var(--primary);outline-offset:1px}
.extract-cell input:disabled{opacity:.6}
.extract-result{min-width:0;line-height:1.6;overflow-wrap:anywhere}
.extract-value{display:block;max-height:120px;overflow:auto;scrollbar-width:thin;scrollbar-color:var(--border) transparent;color:var(--pass-fg);font:12px/1.6 ui-monospace,Consolas,monospace;white-space:pre-wrap}
.extract-failure,.extract-error{color:var(--fail-fg)}.extract-pending,.extract-hint{color:var(--text-muted)}
.extract-remove{display:flex;align-items:center;justify-content:center;width:30px;height:30px;padding:6px;border:0;border-radius:5px;background:none;color:var(--text-muted);cursor:pointer}
.extract-remove svg{width:16px;height:16px}.extract-remove:hover{color:var(--fail-fg);background:var(--fail-bg)}
.extract-add{display:inline-flex;align-items:center;gap:5px;margin-top:8px;padding:4px 0;border:0;background:none;color:var(--primary);font:inherit;cursor:pointer}
.extract-add span{font-size:17px}.extract-add:focus-visible,.extract-remove:focus-visible{outline:2px solid var(--primary);outline-offset:2px}
button:disabled{opacity:.45;cursor:not-allowed}.extract-hint,.extract-error{margin:7px 0 0;font-size:11.5px;line-height:1.6;overflow-wrap:anywhere}.mobile-label{display:none}
@media(max-width:600px){.extract-head{display:none}.extract-row{grid-template-columns:minmax(0,1fr) minmax(0,1fr) 28px;gap:8px}.extract-result{grid-column:1/3;grid-row:2}.extract-remove{grid-column:3;grid-row:1/3}.mobile-label{display:block;margin-bottom:5px;color:var(--text-muted);font-size:11px}.extract-result .mobile-label{display:inline;margin-right:8px}}
</style>
