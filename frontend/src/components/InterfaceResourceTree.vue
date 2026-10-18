<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { interfaceResources } from '../utils/interfaceResources'

const props = defineProps({ interfaces: { type: Array, default: () => [] }, cases: { type: Array, default: () => [] }, selected: Object, loading: Boolean, error: String, caseError: String, disabled: Boolean })
const emit = defineEmits(['select-interface', 'select-case', 'create-case', 'create-interface', 'manage-categories', 'retry'])
const keyword = ref('')
const foldedGroups = reactive({}), foldedInterfaces = reactive({})
const groups = computed(() => interfaceResources(props.interfaces, props.cases, keyword.value))
const isSelected = (type, id) => props.selected?.type === type && String(props.selected.id) === String(id)
watch(() => props.selected, selected => {
  if (!selected) return
  if (selected.type === 'new-case') keyword.value = ''
  const id = selected.interfaceId ?? selected.id
  const item = props.interfaces.find(item => String(item.id) === String(id))
  if (item) {
    foldedGroups[item.category?.trim() || '未分类'] = false
    foldedInterfaces[item.id] = false
  }
}, { immediate: true })
</script>

<template>
  <nav class="resource-tree panel" aria-label="接口和测试用例">
    <header class="resource-heading"><strong>接口与用例</strong><div><button type="button" class="tree-tool" title="分类管理" aria-label="分类管理" :disabled="disabled" @click="emit('manage-categories')"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M3 7h6l2-3h10v15H3z" /></svg></button><button type="button" class="tree-tool" title="新建接口" aria-label="新建接口" :disabled="disabled" @click="emit('create-interface')"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 5v14M5 12h14" /></svg></button></div></header>
    <label class="resource-search"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><circle cx="10" cy="10" r="6"/><path d="m15 15 5 5"/></svg><input v-model="keyword" aria-label="搜索接口和用例" placeholder="搜索接口、URL、用例"/><button v-if="keyword" type="button" aria-label="清空搜索" @click="keyword = ''">×</button></label>
    <p class="resource-count">{{ interfaces.length }} 个接口 · {{ cases.length }} 个用例</p>
    <div v-if="loading" class="tree-state" role="status">加载中…</div>
    <div v-else-if="error" class="tree-state tree-error" role="alert">{{ error }}<button class="btn btn-ghost" @click="emit('retry')">重试</button></div>
    <template v-else>
      <div v-if="caseError" class="tree-state tree-error" role="alert">{{ caseError }}<button class="btn btn-ghost" @click="emit('retry')">重试</button></div>
      <div v-if="!interfaces.length" class="tree-state">暂无接口，点击上方「＋」创建。</div>
      <div v-else-if="!groups.length" class="tree-state">没有匹配的接口或用例</div>
      <ul v-else class="resource-groups">
        <li v-for="group in groups" :key="group.name">
          <button class="category-node" type="button" :title="group.name" :aria-expanded="Boolean(keyword.trim()) || !foldedGroups[group.name]" @click="foldedGroups[group.name] = !foldedGroups[group.name]"><svg class="category-chevron" :class="{ folded: !keyword.trim() && foldedGroups[group.name] }" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="m4 6 4 4 4-4"/></svg><svg class="category-folder" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true"><path d="M2.5 5h5l2-2h8v13h-15z"/></svg><span>{{ group.name }}</span><small>{{ group.items.length }}</small></button>
          <ul v-if="keyword.trim() || !foldedGroups[group.name]" class="interface-nodes">
            <li v-for="item in group.items" :key="item.id">
              <div class="interface-node" :class="{ active: isSelected('interface', item.id) }">
                <button type="button" class="disclosure" :aria-label="(foldedInterfaces[item.id] ? '展开' : '收起') + item.name + '的用例'" :aria-expanded="Boolean(keyword.trim()) || !foldedInterfaces[item.id]" @click="foldedInterfaces[item.id] = !foldedInterfaces[item.id]"><svg :class="{ folded: !keyword.trim() && foldedInterfaces[item.id] }" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="m4 6 4 4 4-4"/></svg></button>
                <button type="button" class="interface-select" :aria-current="isSelected('interface', item.id) ? 'true' : undefined" :title="item.method + ' ' + item.url" :disabled="disabled" @click="emit('select-interface', item)"><span class="tree-method" :class="'m-' + (item.method || 'GET').toLowerCase()">{{ item.method }}</span><span class="node-name">{{ item.name }}</span></button>
                <button type="button" class="add-case" :aria-label="'为' + item.name + '新建用例'" title="新建用例" :disabled="disabled || Boolean(caseError)" @click="emit('create-case', item)">+</button>
              </div>
              <ul v-if="keyword.trim() || !foldedInterfaces[item.id]" class="case-nodes">
                <li v-for="testCase in item.cases" :key="testCase.id"><button type="button" class="case-node" :class="{ active: isSelected('case', testCase.id) }" :aria-current="isSelected('case', testCase.id) ? 'true' : undefined" :disabled="disabled" :title="testCase.name" @click="emit('select-case', testCase)"><svg viewBox="0 0 18 18" fill="none" stroke="currentColor" stroke-width="1.4"><path d="M5 2h6l3 3v11H4V2zM7 8h4M7 11h4"/></svg><span class="node-name">{{ testCase.name }}</span><small>{{ testCase.expected_status }}</small></button></li>
                <li v-if="!item.caseCount && !keyword.trim()" class="no-cases">暂无用例</li>
              </ul>
            </li>
          </ul>
        </li>
      </ul>
    </template>
  </nav>
</template>

<style scoped>
.resource-tree{min-width:0;align-self:start;position:sticky;top:20px;max-height:calc(100vh - 140px);overflow:auto;padding-bottom:12px}.resource-heading{padding:14px 12px 10px 16px;display:flex;align-items:center;justify-content:space-between;gap:8px;font-size:14px}.resource-heading>div{display:flex;gap:4px}.tree-tool{width:30px;height:30px;display:grid;place-items:center;border:0;border-radius:6px;background:transparent;color:var(--text-muted);cursor:pointer}.tree-tool svg{width:18px;height:18px}.tree-tool:hover{background:var(--surface-2);color:var(--primary)}.resource-search{display:flex;align-items:center;gap:6px;margin:0 12px;padding:0 8px;height:34px;background:var(--surface-2);border:1px solid var(--border);border-radius:7px}.resource-search:focus-within{border-color:var(--primary)}.resource-search svg{width:15px;height:15px;flex:none;color:var(--text-muted)}.resource-search input{border:0;background:transparent;outline:none;width:100%;min-width:0;color:var(--text);font:12px inherit}.resource-search button{border:0;background:transparent;color:var(--text-muted);cursor:pointer;font-size:18px}.resource-count{padding:0 16px;font-size:11px;color:var(--text-muted);margin:10px 0 12px}.resource-groups,.interface-nodes,.case-nodes{list-style:none;margin:0;padding:0}.resource-groups{padding:0 6px}.resource-groups>li+li{margin-top:4px}.interface-nodes{margin-left:20px}.category-node{border:0;border-radius:6px;background:transparent;width:100%;display:flex;align-items:center;gap:7px;text-align:left;padding:8px 7px;color:var(--text-muted);font-family:inherit;font-size:13px;line-height:20px;font-weight:600;cursor:pointer}.category-node:hover{background:var(--surface-2);color:var(--text)}.category-node span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0}.category-node small{margin-left:auto;flex:none;font-size:11px;font-weight:400}.category-node svg,.disclosure svg{width:14px;height:14px;flex:none;transition:transform .15s}.category-node .category-folder{width:15px;height:15px}.folded{transform:rotate(-90deg)}.interface-node{display:flex;align-items:center;border-radius:6px;padding:2px;min-width:0}.interface-node:hover,.case-node:hover{background:var(--surface-2)}.interface-node.active,.case-node.active{background:var(--surface-2);color:var(--primary)}.interface-select{flex:1;display:flex;align-items:center;gap:7px;min-width:0;padding:6px 0;text-align:left;font-family:inherit;font-size:12px;line-height:20px;color:inherit;border:0;background:transparent;cursor:pointer}.disclosure{display:grid;place-items:center;width:22px;height:30px;flex:none;padding:0;border:0;background:transparent;color:var(--text-muted);cursor:pointer}.tree-method{font:700 9px ui-monospace,Consolas,monospace;flex:none;min-width:36px;color:var(--primary)}.m-get{color:var(--pass-fg)}.m-delete{color:var(--fail-fg)}.m-post{color:var(--warn-fg,var(--primary))}.node-name{overflow:hidden;white-space:nowrap;text-overflow:ellipsis;min-width:0}.add-case{width:26px;height:28px;flex:none;border:0;background:transparent;color:var(--text-muted);border-radius:5px;font-size:18px;cursor:pointer}.add-case:hover{color:var(--primary);background:var(--surface)}@media(hover:hover) and (pointer:fine){.add-case{opacity:0;transition:opacity .15s}.interface-node:hover .add-case,.interface-node:focus-within .add-case{opacity:1}}.case-nodes{margin-left:20px}.case-node{width:100%;display:flex;align-items:center;gap:7px;padding:6px 8px;margin:2px 0;text-align:left;border:0;border-radius:6px;background:transparent;color:var(--text-muted);font-family:inherit;font-size:12px;line-height:20px;cursor:pointer}.case-node svg{width:15px;height:15px;flex:none}.case-node small{margin-left:auto;flex:none;font:10px ui-monospace,Consolas,monospace}.no-cases{font-size:11px;color:var(--text-muted);padding:7px 8px}.tree-state{text-align:center;padding:24px 16px;font-size:12px;color:var(--text-muted);line-height:1.6}.tree-error{color:var(--fail-fg)}.tree-state .btn{margin-top:10px}button:focus-visible{outline:2px solid var(--primary);outline-offset:-2px}button:disabled{cursor:not-allowed;opacity:.5}@media(max-width:760px){.resource-tree{position:static;max-height:300px}}
</style>
