<script setup>
import { computed, ref, watch } from 'vue'
import Modal from './Modal.vue'
import HiddenScrollArea from './HiddenScrollArea.vue'
import SuiteFilterSelect from './SuiteFilterSelect.vue'

const props = defineProps({ cases: { type:Array, required:true }, interfaces: { type:Array, required:true }, remaining: { type:Number, default:1000 } })
const emit = defineEmits(['add', 'close'])
const query = ref(''), interfaceId = ref(''), page = ref(1), chosenIds = ref([])
const pageSize = 20
const ifaceMap = computed(() => new Map(props.interfaces.map(item => [item.id, item])))
const interfaceOptions = computed(() => [{value:'',label:'全部接口'}, ...props.interfaces.map(item => ({value:item.id,label:item.name}))])
const filtered = computed(() => {
  const q = query.value.trim().toLowerCase()
  return props.cases.filter(item => {
    const request = ifaceMap.value.get(item.interface_id)
    return (!interfaceId.value || String(item.interface_id) === String(interfaceId.value)) &&
      `${item.name} ${request?.name || ''} ${request?.url || ''} ${request?.method || ''}`.toLowerCase().includes(q)
  })
})
const pages = computed(() => Math.max(1, Math.ceil(filtered.value.length / pageSize)))
const visible = computed(() => filtered.value.slice((page.value - 1) * pageSize, page.value * pageSize))
const allOnPage = computed(() => visible.value.length > 0 && visible.value.every(item => chosenIds.value.includes(item.id)))
const someOnPage = computed(() => !allOnPage.value && visible.value.some(item => chosenIds.value.includes(item.id)))
const selected = computed(() => chosenIds.value.map(id => props.cases.find(item => item.id === id)).filter(Boolean))
const tooMany = computed(() => selected.value.length > props.remaining)

function toggle(id) {
  chosenIds.value = chosenIds.value.includes(id) ? chosenIds.value.filter(value => value !== id) : [...chosenIds.value, id]
}
function togglePage() {
  const ids = new Set(visible.value.map(item => item.id))
  chosenIds.value = allOnPage.value ? chosenIds.value.filter(id => !ids.has(id)) : [...new Set([...chosenIds.value, ...ids])]
}
function add() { if (selected.value.length && !tooMany.value) emit('add', selected.value) }
watch([query, interfaceId], () => page.value = 1, { flush:'sync' })
</script>

<template>
  <Modal title="从用例库添加步骤" :max-width="820" hide-scrollbar @close="emit('close')">
    <p class="picker-hint">按勾选顺序添加为独立步骤，之后可以修改或拖拽排序。同一用例可以再次添加。</p>
    <div class="picker-filters">
      <input v-model="query" aria-label="搜索用例" placeholder="搜索用例名称、接口或路径…" />
      <SuiteFilterSelect v-model="interfaceId" :options="interfaceOptions" input-id="scenario-case-interface" label="接口筛选" />
    </div>
    <div class="picker-list">
      <HiddenScrollArea :key="`${page}-${query}-${interfaceId}`" label="用例列表，可使用方向键或翻页键滚动">
        <div v-if="!filtered.length" class="picker-empty">{{ cases.length ? '没有匹配的用例，请调整搜索或筛选。' : '还没有用例，请先在接口测试中创建。' }}</div>
        <label v-for="item in visible" :key="item.id" class="case-option" :class="{ checked:chosenIds.includes(item.id) }">
          <input type="checkbox" :checked="chosenIds.includes(item.id)" @change="toggle(item.id)" />
          <span class="case-copy"><strong>{{ item.name }}</strong><small>{{ ifaceMap.get(item.interface_id)?.name || '接口不可用' }}<span>·</span><b>{{ ifaceMap.get(item.interface_id)?.method || '—' }}</b> {{ ifaceMap.get(item.interface_id)?.url }}</small></span>
          <span v-if="chosenIds.includes(item.id)" class="selection-order">{{ chosenIds.indexOf(item.id) + 1 }}</span>
        </label>
      </HiddenScrollArea>
    </div>
    <div class="picker-pagination">
      <label><input type="checkbox" :disabled="!visible.length" :checked="allOnPage" :indeterminate="someOnPage" @change="togglePage" /> 全选本页</label>
      <span>共 {{ filtered.length }} 条</span>
      <div class="page-controls"><button type="button" aria-label="上一页用例" :disabled="page <= 1" @click="page--">‹</button><span>{{ page }} / {{ pages }}</span><button type="button" aria-label="下一页用例" :disabled="page >= pages" @click="page++">›</button></div>
    </div>
    <p v-if="tooMany" class="picker-error" role="alert">当前场景还可添加 {{ remaining }} 个步骤，请减少选择。</p>
    <template #foot>
      <span class="picked-count">已选 {{ selected.length }} 个用例<button v-if="selected.length" type="button" @click="chosenIds = []">清空</button></span>
      <button class="btn btn-ghost" @click="emit('close')">取消</button><button class="btn btn-primary" :disabled="!selected.length || tooMany" @click="add">添加步骤{{ selected.length ? `（${selected.length}）` : '' }}</button>
    </template>
  </Modal>
</template>

<style scoped>
.picker-hint{margin:0 0 16px;color:var(--text-muted);font-size:12px;line-height:1.7}
.picker-filters{display:grid;grid-template-columns:minmax(0,1fr) 210px;gap:10px;margin-bottom:14px}
.picker-filters>input{box-sizing:border-box;min-width:0;height:36px;padding:0 11px;border:1px solid var(--border);border-radius:7px;background:var(--surface-2);color:var(--text);font:inherit;font-size:13px}
.picker-filters :deep(.suite-filter>button){height:36px;font-size:12px}
.picker-list{display:flex;height:340px;max-height:45vh;min-height:160px;border:1px solid var(--border);border-radius:9px;overflow:hidden}
.case-option{display:flex;align-items:center;gap:12px;padding:12px 14px;border-bottom:1px solid var(--border);cursor:pointer;min-height:64px;box-sizing:border-box}
.case-option:last-child{border-bottom:0}
.case-option:hover,.case-option.checked{background:var(--surface-2)}
input[type=checkbox]{accent-color:var(--primary);width:14px;height:14px;flex:none}
.case-copy{min-width:0;flex:1}
.case-copy strong{display:block;overflow-wrap:anywhere;color:var(--text);font-size:13px;font-weight:600}
.case-copy small{display:flex;flex-wrap:wrap;gap:6px;margin-top:5px;overflow-wrap:anywhere;color:var(--text-muted);font-size:11px}
.case-copy b{font-size:10px;font-weight:600}
.selection-order{display:grid;place-items:center;min-width:22px;height:22px;border-radius:50%;color:var(--primary);background:var(--surface);font-size:11px}
.picker-pagination{display:flex;align-items:center;gap:14px;margin-top:12px;font-size:12px;color:var(--text-muted)}
.picker-pagination label{display:flex;align-items:center;gap:6px;cursor:pointer}
.page-controls{display:flex;align-items:center;gap:12px;margin-left:auto}
.page-controls button{width:28px;height:28px;border:1px solid var(--border);border-radius:5px;background:var(--surface);color:var(--text);font-size:18px;cursor:pointer}
.page-controls button:disabled{opacity:.4;cursor:default}
.picked-count{display:flex;align-items:center;gap:8px;margin-right:auto;align-self:center;color:var(--text-muted);font-size:12px}
.picked-count button{padding:0;border:0;background:none;color:var(--primary);font:inherit;cursor:pointer}
.picker-error{color:var(--fail-fg);font-size:12px}
.picker-empty{padding:48px 16px;text-align:center;font-size:12px;color:var(--text-muted)}
button:focus-visible,input:focus-visible{outline:2px solid var(--primary);outline-offset:2px}
@media(max-width:600px){.picker-filters{grid-template-columns:minmax(0,1fr)}
.picker-pagination{flex-wrap:wrap;gap:8px}
.picked-count{font-size:11px}
.picker-list{height:300px}
.case-option{padding:11px 10px;gap:8px}
}
</style>
