<script setup>
import { computed } from 'vue'
import { pathParameterNames } from '../utils/pathParameters'

const props = defineProps({
  url: { type: String, default: '' },
  modelValue: { type: Object, default: () => ({}) },
  disabled: { type: Boolean, default: false },
  idPrefix: { type: String, default: 'path-param' },
})
const emit = defineEmits(['update:modelValue'])
const names = computed(() => pathParameterNames(props.url))

function updateValue(name, value) {
  emit('update:modelValue', Object.fromEntries(names.value.map(key => [
    key, key === name ? value : (Object.hasOwn(props.modelValue, key) ? props.modelValue[key] : ''),
  ])))
}
</script>

<template>
  <div class="path-editor">
    <p v-if="!names.length" class="path-hint">在请求 URL 中填写 /orders/{id}，这里会自动显示路径参数。</p>
    <template v-else>
      <div class="path-head" aria-hidden="true"><span>路径参数</span><span>参数值</span></div>
      <div v-for="(name, index) in names" :key="name" class="path-row">
        <label :for="idPrefix + '-' + index"><code>{{ name }}</code><span>必填</span></label>
        <input
          :id="idPrefix + '-' + index"
          type="text"
          :value="Object.hasOwn(modelValue, name) ? modelValue[name] : ''"
          :aria-label="'路径参数 ' + name"
          :disabled="disabled"
          placeholder="填写参数值，如 1"
          autocomplete="off"
          @input="updateValue(name, $event.target.value)"
        />
      </div>
      <p class="path-hint">参数名随 URL 自动识别；参数值可直接填写，也支持 ${变量名}。</p>
    </template>
  </div>
</template>

<style scoped>
.path-head,.path-row{display:grid;grid-template-columns:minmax(100px,.7fr) minmax(0,1.3fr);gap:12px;align-items:center}
.path-head{padding:9px 4px;background:var(--surface-2);font-size:11px;font-weight:600;color:var(--text-muted);border-bottom:1px solid var(--border)}
.path-row{padding:10px 4px;border-bottom:1px solid var(--border)}
.path-row label{display:flex;align-items:center;gap:8px;min-width:0;margin:0;font-size:12px}
.path-row code{overflow-wrap:anywhere;color:var(--text);font:12.5px ui-monospace,Consolas,monospace}
.path-row label span{flex:none;color:var(--text-muted);font-size:10px;font-weight:400}
.path-row input{width:100%;min-width:0;height:36px;padding:0 10px;border:1px solid var(--border);border-radius:7px;background:var(--surface);color:var(--text);font:12.5px ui-monospace,Consolas,monospace}
.path-row input:focus{outline:2px solid var(--primary);outline-offset:1px}
.path-row input:disabled{opacity:.6}
.path-hint{margin:10px 0 0;font-size:12px;line-height:1.6;color:var(--text-muted)}
</style>
