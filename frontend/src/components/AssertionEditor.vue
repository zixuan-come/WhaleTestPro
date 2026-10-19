<script setup>
import { computed, ref } from 'vue'
import { ASSERTION_TARGETS, ASSERTION_OPERATORS, newAssertionRow, assertionRows, blankAssertion, serializeAssertions, matchingAssertionResult, formatAssertionValue } from '../utils/assertionRules'
const props = defineProps({ modelValue: { type: [Array, String], default: () => [] }, idPrefix: { type: String, required: true },
  disabled: Boolean, allowDatabase: { type: Boolean, default: true }, strict: Boolean,
  results: { type: Array, default: () => [] }, resultRules: { type: Array, default: () => [] },
  resultsEnabled: { type: Boolean, default: true } })
const emit = defineEmits(['update:modelValue'])
const touched = ref(false)
const rows = computed(() => { const list = assertionRows(props.modelValue); return list.length ? list : [newAssertionRow()] })
const targets = computed(() => ASSERTION_TARGETS.filter(item => props.allowDatabase || item.value !== 'database'))
const validation = computed(() => {
  try { serializeAssertions(props.modelValue, { allowDatabase: props.allowDatabase, strict: props.strict }); return '' }
  catch (e) { return e.message }
})
function update(index, key, value) {
  const next = rows.value.map(row => ({ ...row }))
  if (key === 'target') next[index] = newAssertionRow(value)
  else {
    next[index][key] = value
    if (key === 'expectedType') next[index].expectedText = value === 'boolean' ? 'true' : value === 'null' ? '' : next[index].expectedText
  }
  emit('update:modelValue', next)
}
function add() { const list = assertionRows(props.modelValue); emit('update:modelValue', [...list, newAssertionRow('json')]) }
function remove(index) { emit('update:modelValue', rows.value.filter((_, i) => i !== index)) }
function resultFor(row, index) {
  if (!props.resultsEnabled) return null
  const wireIndex = rows.value.slice(0, index).filter(item => !blankAssertion(item)).length
  return matchingAssertionResult(row, wireIndex, props.resultRules, props.results)
}
const operators = row => ASSERTION_OPERATORS[row.target] || []
const schemaExample = JSON.stringify({ type: 'object', required: ['id'] })
const valueExample = JSON.stringify({ id: 42 })
</script>
<template>
  <div class="assertion-editor" role="group" aria-label="业务断言配置" @focusout="touched = true">
    <div class="assertion-head" aria-hidden="true"><span>断言对象</span><span>字段 / 表达式</span><span>判断条件</span><span>期望值</span><span>实际值 / 结果</span><span></span></div>
    <div v-for="(row, index) in rows" :key="index" class="assertion-entry">
      <div class="assertion-row">
        <label><span class="mobile-label">断言对象</span><select :id="`${idPrefix}-target-${index}`" :value="row.target" :disabled="disabled" :aria-label="`第 ${index + 1} 条断言对象`" @change="update(index, 'target', $event.target.value)"><option value="" disabled>选择对象</option><option v-for="item in targets" :key="item.value" :value="item.value">{{ item.label }}</option><option v-if="row.target === 'database' && !allowDatabase" value="database">数据库（不支持）</option><option v-if="row.target === 'custom'" value="custom">旧配置</option></select></label>
        <label><span class="mobile-label">字段 / 表达式</span><input v-if="['json','header'].includes(row.target)" :id="`${idPrefix}-path-${index}`" :value="row.path" :disabled="disabled" :aria-label="`第 ${index + 1} 条断言字段`" :placeholder="row.target === 'json' ? '$.data.id' : 'Content-Type'" spellcheck="false" @input="update(index, 'path', $event.target.value)" /><span v-else class="field-note">{{ row.target === 'time' ? '耗时（ms）' : ['database','schema','custom'].includes(row.target) ? '在下方配置' : '—' }}</span></label>
        <label><span class="mobile-label">判断条件</span><select :id="`${idPrefix}-operator-${index}`" :value="row.operator" :class="{ 'single-operator': operators(row).length === 1 }" :disabled="disabled || !row.target || operators(row).length < 2" :aria-label="`第 ${index + 1} 条判断条件`" @change="update(index, 'operator', $event.target.value)"><option v-for="[value, text] in operators(row)" :key="value" :value="value">{{ text }}</option><option v-if="!row.target" value="eq">—</option></select></label>
        <div class="expected-cell"><span class="mobile-label">期望值</span><template v-if="!['schema','custom'].includes(row.target)">
          <select :id="`${idPrefix}-value-type-${index}`" :value="row.expectedType" :disabled="disabled || !row.target" :aria-label="`第 ${index + 1} 条期望值类型`" @change="update(index, 'expectedType', $event.target.value)"><option value="string">文本</option><option value="number">数字</option><option value="boolean">布尔</option><option value="null">null</option><option value="json">JSON</option><option v-if="row.expectedType === 'missing'" value="missing" disabled>请选择</option></select>
          <select v-if="row.expectedType === 'boolean'" :id="`${idPrefix}-expected-${index}`" :value="row.expectedText" :disabled="disabled" :aria-label="`第 ${index + 1} 条期望值`" @change="update(index, 'expectedText', $event.target.value)"><option value="true">true</option><option value="false">false</option></select>
          <span v-else-if="row.expectedType === 'null'" class="field-note">null</span>
          <input v-else-if="row.expectedType !== 'json'" :id="`${idPrefix}-expected-${index}`" :value="row.expectedText" :disabled="disabled || !row.target" :aria-label="`第 ${index + 1} 条期望值`" :inputmode="row.expectedType === 'number' ? 'decimal' : 'text'" :placeholder="row.target === 'time' ? '如 1000' : '期望值'" @input="update(index, 'expectedText', $event.target.value)" />
          <span v-else class="field-note">下方编辑 JSON</span>
        </template><span v-else class="field-note">在下方配置</span></div>
        <div class="assertion-result" aria-live="polite"><span class="mobile-label">实际值 / 结果</span><template v-if="resultFor(row, index)"><code>{{ formatAssertionValue(resultFor(row, index).actual) }}</code><span :class="resultFor(row, index).passed ? 'passed' : 'failed'">{{ resultFor(row, index).passed ? '通过' : '失败' }}</span></template><span v-else class="field-note">待执行</span></div>
        <button class="assertion-remove" type="button" :disabled="disabled" :aria-label="`删除第 ${index + 1} 条断言`" title="删除断言" @click="remove(index)"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13M10 10v7m4-7v7" /></svg></button>
      </div>
      <div v-if="row.target === 'database'" class="assertion-expanded"><label :for="`${idPrefix}-sql-${index}`">查询 SQL · 只读 SELECT</label><textarea :id="`${idPrefix}-sql-${index}`" :value="row.path" :disabled="disabled" rows="3" placeholder="SELECT COUNT(*) FROM orders WHERE id = 42" @input="update(index, 'path', $event.target.value)" /></div>
      <div v-if="row.target === 'schema' || row.expectedType === 'json' && row.target !== 'custom'" class="assertion-expanded"><label :for="`${idPrefix}-json-${index}`">{{ row.target === 'schema' ? 'JSON Schema' : '期望值 · JSON' }}</label><textarea :id="`${idPrefix}-json-${index}`" :value="row.expectedText" :disabled="disabled" rows="4" :placeholder="row.target === 'schema' ? schemaExample : valueExample" spellcheck="false" @input="update(index, 'expectedText', $event.target.value)" /></div>
      <div v-if="row.target === 'custom'" class="assertion-expanded"><label :for="`${idPrefix}-legacy-${index}`">旧断言配置 · 保留原内容，可修改或删除</label><textarea :id="`${idPrefix}-legacy-${index}`" :value="row.rawText" :disabled="disabled" rows="4" spellcheck="false" @input="update(index, 'rawText', $event.target.value)" /></div>
    </div>
    <button class="assertion-add" type="button" :disabled="disabled" @click="add"><span aria-hidden="true">＋</span> 添加断言</button>
    <p v-if="touched && validation" class="assertion-error" role="alert">{{ validation }}</p>
    <p class="assertion-hint">期望值按所选类型比较；运行后查看实际值和结果，修改配置后需重新执行。状态码使用上方的“期望状态码”。</p>
  </div>
</template>
<style scoped>
.assertion-editor{container-type:inline-size;min-width:0;font-size:12px;color:var(--text)}.assertion-head,.assertion-row{display:grid;grid-template-columns:minmax(90px,.95fr) minmax(100px,1.1fr) minmax(75px,.8fr) minmax(145px,1.5fr) minmax(78px,.9fr) 28px;gap:8px;align-items:center}.assertion-head{padding:8px 0;color:var(--text-muted);font-size:11.5px;border-bottom:1px solid var(--border)}.assertion-entry{padding:8px 0;border-bottom:1px solid var(--border)}label{display:block;min-width:0;margin:0;font-weight:400}.expected-cell{display:flex;gap:5px;align-items:center;min-width:0}.expected-cell>select:first-of-type{flex:0 0 62px;width:62px}.expected-cell>input,.expected-cell>select:not(:first-of-type){flex:1;min-width:0}.assertion-editor :is(input,select,textarea){box-sizing:border-box;min-width:0;width:100%;height:34px;padding:0 7px;color:var(--text);background:var(--surface);border:1px solid var(--border);border-radius:6px;font-family:inherit;font-size:12px}.assertion-editor input{font-family:ui-monospace,Consolas,monospace}.assertion-editor select{cursor:pointer}.assertion-editor :is(input,select,textarea):focus-visible{outline:2px solid var(--primary);outline-offset:1px}.assertion-editor :disabled{opacity:.55;cursor:not-allowed}.assertion-editor .single-operator:disabled{opacity:1;color:var(--text)}.field-note{display:block;color:var(--text-muted);font-size:11.5px;line-height:1.6;overflow-wrap:anywhere}.assertion-result{min-width:0;overflow-wrap:anywhere;line-height:1.6}.assertion-result code{display:block;max-height:110px;overflow:auto;scrollbar-width:thin;scrollbar-color:var(--border) transparent;white-space:pre-wrap;font:11.5px/1.6 ui-monospace,Consolas,monospace}.assertion-result .passed{color:var(--pass-fg)}.assertion-result .failed,.assertion-error{color:var(--fail-fg)}.assertion-remove{display:flex;align-items:center;justify-content:center;width:28px;height:30px;padding:6px;background:none;border:0;border-radius:5px;color:var(--text-muted);cursor:pointer}.assertion-remove svg{width:16px;height:16px}.assertion-remove:hover{color:var(--fail-fg);background:var(--fail-bg)}.assertion-add{display:inline-flex;gap:5px;align-items:center;margin-top:8px;padding:4px 0;color:var(--primary);background:none;border:0;font:inherit;cursor:pointer}.assertion-add span{font-size:17px}.assertion-add:focus-visible,.assertion-remove:focus-visible{outline:2px solid var(--primary);outline-offset:2px}.assertion-expanded{margin-top:10px}.assertion-expanded label{margin-bottom:6px;font-size:11.5px;color:var(--text-muted)}.assertion-editor textarea{height:auto;padding:8px 10px;resize:vertical;font:12px/1.6 ui-monospace,Consolas,monospace}.assertion-hint,.assertion-error{margin:7px 0 0;font-size:11.5px;line-height:1.6;overflow-wrap:anywhere}.assertion-hint{color:var(--text-muted)}.mobile-label{display:none}
@container(max-width:580px){.assertion-head{display:none}.assertion-row{grid-template-columns:minmax(0,1fr) minmax(0,1fr) 28px;gap:9px 8px;align-items:start}.mobile-label{display:block;margin-bottom:5px;color:var(--text-muted);font-size:11px}.assertion-row>label:first-child{grid-column:1;grid-row:1}.assertion-row>label:nth-child(2){grid-column:2;grid-row:1}.assertion-row>label:nth-child(3){grid-column:1;grid-row:2}.expected-cell{grid-column:2;grid-row:2;display:grid;grid-template-columns:62px minmax(0,1fr)}.expected-cell>.mobile-label{grid-column:1/-1;margin-bottom:0}.assertion-result{grid-column:1/3;grid-row:3}.assertion-result>.mobile-label{display:inline;margin-right:8px}.assertion-result code{display:inline}.assertion-result>span:last-child{margin-left:6px}.assertion-remove{grid-column:3;grid-row:1/4;align-self:center}.field-note{min-height:34px;display:flex;align-items:center}.assertion-result .field-note{display:inline;min-height:0}}
@container(max-width:300px){.expected-cell{grid-template-columns:1fr}.expected-cell>select:first-of-type{width:100%}.expected-cell>.mobile-label{grid-column:auto}}
</style>
