<script setup>
import { computed, ref, watch } from 'vue'
import KeyValueEditor from './KeyValueEditor.vue'
import PathParameterEditor from './PathParameterEditor.vue'
import { pathParameterNames } from '../utils/pathParameters'

const props = defineProps({
  modelValue: { type: Object, required: true }, url: { type: String, default: '' },
  disabled: { type: Boolean, default: false }, idPrefix: { type: String, default: 'request' },
})
const emit = defineEmits(['update:modelValue'])
const names = computed(() => pathParameterNames(props.url))
const tab = ref(names.value.length ? 'path' : 'params')
const tabs = computed(() => [
  { key: 'path', name: 'Path 参数', count: names.value.length },
  { key: 'params', name: 'Query 参数', count: props.modelValue.params.filter(row => row.enabled && row.key.trim()).length },
  { key: 'headers', name: 'Headers', count: props.modelValue.headers.filter(row => row.enabled && row.key.trim()).length },
  { key: 'body', name: 'Body', count: props.modelValue.bodyType === 'json' ? 'JSON' : 'none' },
])
watch(() => props.url, () => { if (names.value.length) tab.value = 'path' })
function update(field, value) { emit('update:modelValue', { ...props.modelValue, [field]: value }) }
function setBodyType(type) {
  emit('update:modelValue', { ...props.modelValue, bodyType: type, body: type === 'json' && !props.modelValue.body.trim() ? '{}' : props.modelValue.body })
}
function focusError(error) { if (error?.tab) tab.value = error.tab }
defineExpose({ focusError })
</script>

<template>
  <fieldset class="request-editor" :disabled="disabled">
    <legend class="sr-only">请求参数配置</legend>
    <div class="editor-tabs" role="tablist" aria-label="请求参数">
      <button v-for="item in tabs" :id="idPrefix + '-tab-' + item.key" :key="item.key" type="button" role="tab" :aria-selected="tab === item.key" :aria-controls="idPrefix + '-panel-' + item.key" :class="{ active: tab === item.key }" @click="tab = item.key">
        {{ item.name }} <span>{{ item.count }}</span>
      </button>
    </div>
    <div v-show="tab === 'path'" :id="idPrefix + '-panel-path'" role="tabpanel" :aria-labelledby="idPrefix + '-tab-path'" class="editor-panel">
      <PathParameterEditor :url="url" :model-value="modelValue.pathParams" :disabled="disabled" :id-prefix="idPrefix + '-path'" @update:model-value="update('pathParams', $event)" />
    </div>
    <div v-show="tab === 'params'" :id="idPrefix + '-panel-params'" role="tabpanel" :aria-labelledby="idPrefix + '-tab-params'" class="editor-panel">
      <KeyValueEditor :model-value="modelValue.params" name-label="参数名" value-label="参数值" name-placeholder="如 page" @update:model-value="update('params', $event)" />
    </div>
    <div v-show="tab === 'headers'" :id="idPrefix + '-panel-headers'" role="tabpanel" :aria-labelledby="idPrefix + '-tab-headers'" class="editor-panel">
      <KeyValueEditor :model-value="modelValue.headers" name-label="Header 名称" value-label="Header 值" name-placeholder="如 Authorization" @update:model-value="update('headers', $event)" />
    </div>
    <div v-show="tab === 'body'" :id="idPrefix + '-panel-body'" role="tabpanel" :aria-labelledby="idPrefix + '-tab-body'" class="editor-panel">
      <div class="editor-body-types">
        <label v-for="type in ['none', 'json']" :key="type"><input type="radio" :name="idPrefix + '-body-type'" :value="type" :checked="modelValue.bodyType === type" @change="setBodyType(type)" />{{ type === 'json' ? 'JSON' : 'none' }}</label>
      </div>
      <label v-if="modelValue.bodyType === 'json'" class="body-label">JSON 请求体
        <textarea :value="modelValue.body" rows="7" spellcheck="false" placeholder='{"name":"test"}' :aria-label="idPrefix + ' JSON 请求体'" @input="update('body', $event.target.value)"></textarea>
      </label>
      <p v-else class="editor-hint">此请求不发送 Body。</p>
    </div>
  </fieldset>
</template>

<style scoped>
.request-editor{min-width:0;margin:0;padding:0;border:1px solid var(--border);border-radius:10px;overflow:hidden}.sr-only{position:absolute;width:1px;height:1px;padding:0;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
.editor-tabs{display:flex;gap:4px;padding:6px 8px 0;background:var(--surface-2);border-bottom:1px solid var(--border);overflow-x:auto}.editor-tabs button{flex:none;display:flex;align-items:center;gap:7px;min-height:38px;padding:8px 12px;border:1px solid transparent;border-bottom:0;border-radius:7px 7px 0 0;background:transparent;color:var(--text-muted);font:12px inherit;cursor:pointer}.editor-tabs button.active{background:var(--surface);color:var(--primary);border-color:var(--border)}.editor-tabs span{font-size:10px;color:var(--text-muted)}.editor-tabs button:focus-visible{outline:2px solid var(--primary);outline-offset:-2px}
.editor-panel{padding:14px;background:var(--surface)}.editor-body-types{display:flex;gap:18px;margin-bottom:12px;font-size:12px}.editor-body-types label{display:flex;align-items:center;gap:6px}.editor-body-types input{accent-color:var(--primary)}.body-label{display:block;font-size:12px;color:var(--text)}.body-label textarea{display:block;width:100%;min-width:0;margin-top:8px;padding:10px;border:1px solid var(--border);border-radius:8px;background:var(--surface-2);color:var(--text);font:12.5px/1.6 ui-monospace,Consolas,monospace;resize:vertical}.body-label textarea:focus-visible{outline:2px solid var(--primary);outline-offset:1px}.editor-hint{margin:6px 0;color:var(--text-muted);font-size:12px}.request-editor:disabled{opacity:.7}
@media(max-width:560px){.editor-panel{padding:10px}.editor-tabs{gap:0;padding-left:3px;padding-right:3px}.editor-tabs button{padding:8px 9px}}
</style>
