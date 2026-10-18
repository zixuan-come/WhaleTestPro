<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useAuthStore } from '../stores/auth'
import { listScenarios } from '../api/scenario'
import { listCases } from '../api/case'
import { listInterfaces } from '../api/interface'
import { filterSuiteContent, selectedSuiteContent, suiteCatalog } from '../utils/suiteSelection'
import HiddenScrollArea from './HiddenScrollArea.vue'
import SuiteFilterSelect from './SuiteFilterSelect.vue'

const props = defineProps({ modelValue: { type:Object, required:true }, disabled:Boolean })
const emit = defineEmits(['update:modelValue', 'ready'])
const auth = useAuthStore(), catalog = ref({ scenarios:[], cases:[], interfaces:[], tags:[] })
const loading = ref(true), error = ref(''), notice = ref(''), kind = ref('scenario'), query = ref(''), interfaceId = ref(''), tag = ref('')
const page = ref(1), pageSize = ref(20), selectedQuery = ref(''), mobilePane = ref('available')
const dynamicEnabled = ref(!!props.modelValue.tags?.length)
const identity = computed(() => `${auth.username}:${auth.currentProjectId}:${auth.token}`)
const chosen = computed(() => selectedSuiteContent(catalog.value, props.modelValue))
const filtered = computed(() => filterSuiteContent(catalog.value, { kind:kind.value, query:query.value, interfaceId:interfaceId.value, tag:tag.value }))
const pages = computed(() => Math.max(1, Math.ceil(filtered.value.length / pageSize.value)))
const visible = computed(() => filtered.value.slice((page.value - 1) * pageSize.value, page.value * pageSize.value))
const selectionKey = computed(() => kind.value === 'scenario' ? 'scenario_ids' : 'case_ids')
const selectedCount = computed(() => (props.modelValue.scenario_ids?.length || 0) + (props.modelValue.case_ids?.length || 0))
const eligible = computed(() => visible.value.filter(item => kind.value !== 'case' || !chosen.value.included.has(item.id)))
const allOnPage = computed(() => !!eligible.value.length && eligible.value.every(item => (props.modelValue[selectionKey.value] || []).includes(item.id)))
const someOnPage = computed(() => !allOnPage.value && eligible.value.some(item => (props.modelValue[selectionKey.value] || []).includes(item.id)))
const selectedScenarios = computed(() => chosen.value.scenarios.filter(matchesSelected))
const selectedCases = computed(() => chosen.value.cases.filter(matchesSelected))
const selectedDynamic = computed(() => chosen.value.dynamic.filter(matchesSelected))
const hasSelectedMatches = computed(() => selectedScenarios.value.length + selectedCases.value.length + selectedDynamic.value.length > 0)
const tagOptions = computed(() => [...new Set([...catalog.value.tags, ...(props.modelValue.tags || [])])])
let requestVersion = 0
function matchesSelected(item) { return `${item.name} ${item.interface_name || ''}`.toLowerCase().includes(selectedQuery.value.trim().toLowerCase()) }
async function load() {
  const version = ++requestVersion, context = identity.value
  loading.value = true; error.value = ''; emit('ready', false)
  try {
    if (!auth.token || !auth.currentProjectId) throw Error('请先选择项目')
    const data = await Promise.all([listScenarios(), listCases(), listInterfaces()])
    if (version !== requestVersion || context !== identity.value) return
    if (data.some(items => !Array.isArray(items))) throw Error('测试内容加载异常，请重试')
    catalog.value = suiteCatalog(...data)
    emit('ready', true)
  } catch (failure) {
    if (version === requestVersion && context === identity.value) error.value = failure.message || '测试内容加载失败'
  } finally { if (version === requestVersion) loading.value = false }
}
function update(key, values) { emit('update:modelValue', { ...props.modelValue, [key]:values }) }
function setKind(value) { kind.value = value; query.value = ''; interfaceId.value = ''; tag.value = ''; page.value = 1; notice.value = '' }
function toggleItem(item) {
  if (props.disabled || loading.value || error.value) return
  const key = selectionKey.value, ids = props.modelValue[key] || []
  if (ids.includes(item.id)) { update(key, ids.filter(id => id !== item.id)); return }
  if (kind.value === 'case' && chosen.value.included.has(item.id)) return
  if (ids.length >= 100) { notice.value = '每个套件最多选择 100 个场景、100 个独立用例。'; return }
  notice.value = ''; update(key, [...ids, item.id])
}
function togglePage() {
  if (props.disabled || loading.value || error.value) return
  const key = selectionKey.value, ids = props.modelValue[key] || [], currentIds = new Set(eligible.value.map(item => item.id))
  if (allOnPage.value) update(key, ids.filter(id => !currentIds.has(id)))
  else {
    const next = [...new Set([...ids, ...currentIds])]
    if (next.length > 100) { notice.value = '本页选择会超过 100 项上限，请减少选择或拆分套件。'; return }
    update(key, next)
  }
  notice.value = ''
}
function remove(key, id) { if (!props.disabled) update(key, (props.modelValue[key] || []).filter(value => value !== id)) }
function moveScenario(id, direction) {
  if (props.disabled) return
  const ids = [...(props.modelValue.scenario_ids || [])], index = ids.indexOf(id), target = index + direction
  if (index < 0 || target < 0 || target >= ids.length) return
  ;[ids[index], ids[target]] = [ids[target], ids[index]]
  update('scenario_ids', ids)
}
function clear() {
  if (props.disabled) return
  dynamicEnabled.value = false
  emit('update:modelValue', { scenario_ids:[], case_ids:[], tags:[] })
}
function toggleDynamic() { if (!dynamicEnabled.value) update('tags', []) }
function toggleTag(value) {
  if (props.disabled) return
  const tags = props.modelValue.tags || []
  if (tags.includes(value)) update('tags', tags.filter(tag => tag !== value))
  else if (tags.length < 20) update('tags', [...tags, value])
  else notice.value = '自动加入规则最多选择 20 个标签。'
}
function changePage(value) { if (value >= 1 && value <= pages.value) page.value = value }
watch([kind, query, interfaceId, tag, pageSize], () => page.value = 1, { flush:'sync' })
watch(() => props.modelValue.tags, tags => { if (tags?.length) dynamicEnabled.value = true })
watch(identity, () => { requestVersion++; emit('ready', false); catalog.value = { scenarios:[], cases:[], interfaces:[], tags:[] }; load() }, { flush:'sync' })
onMounted(load)
onBeforeUnmount(() => requestVersion++)
</script>

<template>
  <div class="suite-picker">
    <div class="picker-mobile-tabs" role="group" aria-label="内容区域"><button type="button" :aria-pressed="mobilePane === 'available'" @click="mobilePane = 'available'">选择内容</button><button type="button" :aria-pressed="mobilePane === 'selected'" @click="mobilePane = 'selected'">已选清单（{{ selectedCount }}）</button></div>
    <p v-if="notice" class="picker-notice" role="alert">{{ notice }}</p>
    <div class="picker-columns">
      <section class="picker-pane available-pane" :class="{ 'mobile-hidden': mobilePane !== 'available' }" aria-label="可选测试内容">
        <div class="pane-head"><strong>可选内容</strong><div class="kind-tabs" role="group" aria-label="内容类型"><button type="button" :aria-pressed="kind === 'scenario'" @click="setKind('scenario')">场景 {{ catalog.scenarios.length }}</button><button type="button" :aria-pressed="kind === 'case'" @click="setKind('case')">用例 {{ catalog.cases.length }}</button></div></div>
        <div class="picker-search"><input v-model="query" :disabled="disabled" aria-label="搜索可选内容" :placeholder="kind === 'scenario' ? '搜索场景名称…' : '搜索用例名称或所属接口…'" /><div v-if="kind === 'case'" class="candidate-filters"><SuiteFilterSelect v-model="interfaceId" :disabled="disabled" input-id="suite-interface-options" label="接口筛选" :options="[{value:'',label:'全部接口'}, ...catalog.interfaces]" /><SuiteFilterSelect v-model="tag" :disabled="disabled" input-id="suite-tag-options" label="标签筛选" :options="[{value:'',label:'全部标签'}, ...catalog.tags.map(value => ({value,label:value}))]" /></div></div>
        <div v-if="loading" class="picker-state" role="status">正在加载测试内容…</div>
        <div v-else-if="error" class="picker-state error" role="alert">{{ error }}<button type="button" class="picker-link" @click="load">重试</button></div>
        <template v-else>
          <HiddenScrollArea :key="`${kind}-${page}-${pageSize}-${query}-${interfaceId}-${tag}`" label="可选内容列表，可使用上下方向键或翻页键滚动">
            <div v-if="!filtered.length" class="picker-empty">{{ (kind === 'scenario' ? catalog.scenarios : catalog.cases).length ? '没有匹配内容，请调整搜索或筛选。' : kind === 'scenario' ? '还没有场景，可以先添加独立用例。' : '还没有测试用例，请先在接口测试中创建。' }}</div>
            <label v-for="item in visible" :key="item.id" class="candidate-row" :class="{ checked:(modelValue[selectionKey] || []).includes(item.id), included:kind === 'case' && chosen.included.has(item.id) }"><input type="checkbox" :disabled="disabled || (kind === 'case' && chosen.included.has(item.id) && !(modelValue.case_ids || []).includes(item.id))" :checked="(modelValue[selectionKey] || []).includes(item.id) || (kind === 'case' && chosen.included.has(item.id))" @change="toggleItem(item)" /><span class="candidate-copy"><strong>{{ item.name }}</strong><small v-if="kind === 'case'">所属接口：{{ item.interface_name }}</small><small v-else>{{ item.steps.length }} 个步骤</small><small v-if="kind === 'case' && chosen.included.has(item.id)" class="included-note">已包含在所选场景中，不会重复执行</small><details v-if="kind === 'scenario' && item.steps.length" class="scenario-steps"><summary>查看步骤</summary><ol><li v-for="(step, index) in item.steps" :key="index">{{ step.name }}</li></ol></details></span></label>
          </HiddenScrollArea>
          <div class="candidate-footer"><label class="check-page"><input type="checkbox" :disabled="disabled || !eligible.length" :checked="allOnPage" :indeterminate="someOnPage" @change="togglePage" /> 全选本页</label><span>共 {{ filtered.length }} 条</span><div class="page-size" role="group" aria-label="每页数量"><span>每页</span><button v-for="size in [20,50]" :key="size" type="button" :aria-pressed="pageSize === size" @click="pageSize = size">{{ size }}</button></div><div class="picker-pagination"><button type="button" :disabled="disabled || page <= 1" aria-label="上一页可选内容" @click="changePage(page - 1)">‹</button><span>{{ page }} / {{ pages }}</span><button type="button" :disabled="disabled || page >= pages" aria-label="下一页可选内容" @click="changePage(page + 1)">›</button></div></div>
        </template>
      </section>
      <section class="picker-pane selected-pane" :class="{ 'mobile-hidden': mobilePane !== 'selected' }" aria-label="已选测试内容">
        <div class="pane-head"><strong>已选内容 <span>{{ selectedCount }} 项</span></strong><button type="button" class="picker-link" :disabled="disabled || (!selectedCount && !modelValue.tags?.length)" @click="clear">清空已选</button></div>
        <div class="picker-search"><input v-model="selectedQuery" aria-label="搜索已选内容" placeholder="搜索已选名称…" /></div>
        <HiddenScrollArea label="已选内容列表，可使用上下方向键或翻页键滚动">
          <p v-if="!hasSelectedMatches" class="picker-empty">{{ selectedQuery ? '没有匹配的已选内容。' : '勾选场景或用例后，这里会显示完整清单。' }}</p>
          <div v-if="selectedScenarios.length" class="chosen-group"><h4>场景（{{ chosen.scenarios.length }}）</h4><div v-for="item in selectedScenarios" :key="item.id" class="chosen-row"><div><strong :class="{ error:item.missing }">{{ item.name }}</strong><small v-if="item.steps.length">{{ item.steps.map(step => step.name).join(' → ') }}</small></div><div class="chosen-actions"><button type="button" :aria-label="`上移场景 ${item.name}`" :disabled="disabled || modelValue.scenario_ids.indexOf(item.id) === 0" @click="moveScenario(item.id, -1)">↑</button><button type="button" :aria-label="`下移场景 ${item.name}`" :disabled="disabled || modelValue.scenario_ids.indexOf(item.id) === modelValue.scenario_ids.length - 1" @click="moveScenario(item.id, 1)">↓</button><button type="button" :aria-label="`移除场景 ${item.name}`" @click="remove('scenario_ids', item.id)">移除</button></div></div></div>
          <div v-if="selectedCases.length" class="chosen-group"><h4>独立用例（{{ chosen.cases.length }}）</h4><div v-for="item in selectedCases" :key="item.id" class="chosen-row"><div><strong :class="{error:item.missing}">{{ item.name }}</strong><small>{{ item.included ? '已包含在场景中，执行时自动去重' : item.interface_name }}</small></div><button type="button" class="picker-link" :aria-label="`移除用例 ${item.name}`" @click="remove('case_ids', item.id)">移除</button></div></div>
          <div v-if="selectedDynamic.length" class="chosen-group"><h4>标签自动加入（{{ chosen.dynamic.length }}）</h4><div v-for="item in selectedDynamic" :key="item.id" class="chosen-row dynamic-row"><div><strong>{{ item.name }}</strong><small>由标签规则自动加入</small></div></div></div>
        </HiddenScrollArea>
        <p class="selection-order">先按顺序执行场景，再执行独立用例；标签匹配的用例最后加入并去重。</p>
      </section>
    </div>
    <details class="dynamic-settings" :open="dynamicEnabled"><summary>高级设置<span v-if="modelValue.tags?.length"> · 已启用标签规则</span></summary><label class="dynamic-toggle"><input v-model="dynamicEnabled" :disabled="disabled" type="checkbox" @change="toggleDynamic" /> 自动加入带指定标签的用例</label><template v-if="dynamicEnabled"><p>匹配任一标签即可加入；以后新增的匹配用例也会自动进入执行范围。</p><div class="dynamic-tags"><button v-for="value in tagOptions" :key="value" type="button" :disabled="disabled" :aria-pressed="(modelValue.tags || []).includes(value)" @click="toggleTag(value)">{{ value }}</button><span v-if="!tagOptions.length">当前没有可用标签，请先给测试用例添加标签。</span></div><p v-if="modelValue.tags?.length">当前额外匹配 {{ chosen.dynamic.length }} 个独立用例，运行时按最新标签匹配。</p></template></details>
  </div>
</template>

<style scoped>
.suite-picker { display:flex;flex-direction:column;gap:10px;flex:1;min-height:0;min-width:0;color:var(--text); }
.picker-columns { display:grid;grid-template-columns:minmax(0,1.15fr) minmax(0,1fr);gap:14px;flex:1;min-height:205px; }
.picker-pane { display:flex;flex-direction:column;min-width:0;min-height:0;border:1px solid var(--border);border-radius:9px;overflow:hidden;background:var(--surface); }
.pane-head { min-height:43px;padding:9px 12px;display:flex;align-items:center;justify-content:space-between;gap:8px;border-bottom:1px solid var(--border);flex:none; }
.pane-head>strong { font-size:12px;white-space:nowrap; }.pane-head>strong>span { font-weight:400;color:var(--text-muted);font-size:11px; }
.kind-tabs,.picker-mobile-tabs { display:flex;gap:4px; }.kind-tabs button,.picker-mobile-tabs button { padding:5px 8px;border:0;border-radius:4px;background:transparent;color:var(--text-muted);font:inherit;font-size:11px;cursor:pointer; }
.kind-tabs button[aria-pressed=true],.picker-mobile-tabs button[aria-pressed=true] { background:var(--surface-2);color:var(--primary); }
.picker-search { padding:10px 12px;flex:none; }.picker-search>input { width:100%;height:32px;padding:0 9px;border:1px solid var(--border);border-radius:5px;background:var(--surface-2);color:var(--text);font:inherit;font-size:12px; }
.candidate-filters { display:flex;gap:8px;margin-top:8px; }.candidate-row { display:flex;align-items:flex-start;gap:9px;padding:11px 12px;border-bottom:1px solid var(--border);cursor:pointer; }.candidate-row.checked { background:var(--surface-2); }.candidate-row.included { color:var(--text-muted); }.candidate-copy { flex:1;min-width:0; }.candidate-copy strong,.chosen-row strong { font-size:12px;font-weight:600;overflow-wrap:anywhere; }.candidate-copy small,.chosen-row small { display:block;color:var(--text-muted);font-size:11px;line-height:1.6;margin-top:4px;overflow-wrap:anywhere; }.candidate-copy .included-note { color:var(--primary);font-size:10px; }
input[type=checkbox] { width:14px;height:14px;flex:none;accent-color:var(--primary);margin-top:2px; }.scenario-steps { margin-top:5px;font-size:11px;color:var(--text-muted); }.scenario-steps summary { cursor:pointer;width:fit-content;color:var(--primary); }.scenario-steps ol { padding-left:18px;margin:7px 0 0;line-height:1.8; }
.candidate-footer { display:flex;flex-wrap:wrap;align-items:center;gap:9px;padding:10px 12px;border-top:1px solid var(--border);font-size:10px;color:var(--text-muted);flex:none; }.check-page { display:flex;align-items:center;gap:5px;cursor:pointer;white-space:nowrap; }.check-page input{margin:0}.page-size,.picker-pagination { display:flex;align-items:center;gap:4px; }.page-size { margin-left:auto; }.page-size button { border:0;background:transparent;color:var(--text-muted);border-radius:3px;padding:3px;font:inherit;cursor:pointer; }.page-size button[aria-pressed=true] { background:var(--surface-2);color:var(--primary); }.picker-pagination { margin-left:auto; }.picker-pagination button { width:23px;height:23px;border:1px solid var(--border);border-radius:4px;background:var(--surface);color:var(--text);font-size:16px;cursor:pointer; }
.picker-link { border:0;padding:3px;background:transparent;color:var(--primary);font:inherit;font-size:11px;cursor:pointer;white-space:nowrap; }.chosen-group h4 { font-size:11px;font-weight:500;color:var(--text-muted);padding:10px 12px;background:var(--surface-2);margin:0; }.chosen-row { display:flex;align-items:flex-start;gap:7px;padding:11px 12px;border-bottom:1px solid var(--border); }.chosen-row>div:first-child { flex:1;min-width:0; }.chosen-actions { display:flex;align-items:center;gap:3px;flex:none; }.chosen-actions button { border:0;border-radius:4px;padding:3px 4px;background:transparent;color:var(--primary);font:inherit;font-size:11px;cursor:pointer; }.chosen-actions button:hover { background:var(--surface-2); }.selection-order { padding:9px 12px;border-top:1px solid var(--border);margin:0;font-size:10px;line-height:1.6;color:var(--text-muted);flex:none; }.picker-empty,.picker-state { padding:25px 14px;color:var(--text-muted);font-size:12px;line-height:1.8;text-align:center; }.picker-state { flex:1; }.picker-notice { margin:0;font-size:12px;color:var(--fail-fg); }.error { color:var(--fail-fg); }.dynamic-settings { flex:none;font-size:12px; }.dynamic-settings>summary { color:var(--text-muted);cursor:pointer; }.dynamic-toggle { display:flex;align-items:center;gap:7px;margin-top:10px; }.dynamic-settings p { color:var(--text-muted);font-size:11px;line-height:1.6;margin-top:6px; }.dynamic-tags { display:flex;flex-wrap:wrap;gap:6px;max-height:64px;overflow:auto;scrollbar-width:none;margin-top:7px; }.dynamic-tags::-webkit-scrollbar{display:none;width:0;height:0}.dynamic-tags button { padding:4px 8px;border:1px solid var(--border);border-radius:4px;background:var(--surface);color:var(--text-muted);font:inherit;font-size:11px;cursor:pointer; }.dynamic-tags button[aria-pressed=true] { color:var(--primary);border-color:var(--primary); }.dynamic-tags span{font-size:11px;color:var(--text-muted)}button:disabled { opacity:.45;cursor:default; }button:focus-visible,input:focus-visible,summary:focus-visible { outline:2px solid var(--primary);outline-offset:-2px; }.picker-mobile-tabs { display:none; }
@media(max-width:680px) { .picker-mobile-tabs { display:flex;flex:none; }.picker-mobile-tabs button{flex:1;border:1px solid var(--border);padding:7px;font-size:12px}.picker-columns{display:flex;flex-direction:column;min-height:205px}.picker-pane{flex:1}.picker-pane.mobile-hidden{display:none}.dynamic-settings{font-size:11px}.candidate-footer{font-size:10px}.pane-head{padding:9px 10px}.candidate-row,.chosen-row{padding:10px}.kind-tabs button{padding:5px}.candidate-filters{gap:5px} }
</style>
