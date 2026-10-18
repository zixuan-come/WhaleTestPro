<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
const props = defineProps({ modelValue: { type: [String, Number], default: '' }, options: { type: Array, default: () => [] }, label: { type: String, required: true }, inputId: { type: String, required: true }, disabled: Boolean })
const emit = defineEmits(['update:modelValue'])
const root = ref(null), menu = ref(null), searchInput = ref(null), open = ref(false), search = ref(''), active = ref(-1), position = ref({})
const selected = computed(() => props.options.find(option => String(option.value) === String(props.modelValue)))
const filtered = computed(() => props.options.filter(option => option.label.toLowerCase().includes(search.value.trim().toLowerCase())))
function place() {
  if (!root.value) return
  const rect = root.value.getBoundingClientRect(), below = innerHeight - rect.bottom - 12, above = rect.top - 12
  const upward = below < 220 && above > below
  position.value = { left: Math.max(12, Math.min(rect.left, innerWidth - Math.max(220, rect.width) - 12)) + 'px', width: Math.min(Math.max(220, rect.width), innerWidth - 24) + 'px',
    top: (upward ? rect.top - 5 : rect.bottom + 5) + 'px', maxHeight: Math.max(100, Math.min(250, upward ? above : below)) + 'px', transform: upward ? 'translateY(-100%)' : undefined }
}
function close() { open.value = false }
async function toggle() {
  if (props.disabled) return
  if (open.value) return close()
  search.value = ''; active.value = -1; place(); open.value = true
  await nextTick(); searchInput.value?.focus()
}
function pick(option) { emit('update:modelValue', option.value); close(); root.value?.querySelector('button')?.focus() }
async function onKey(event) {
  if (event.isComposing || event.ctrlKey || event.altKey || event.metaKey) return
  if (event.key === 'Escape' && open.value) { event.preventDefault(); event.stopPropagation(); close(); root.value?.querySelector('button')?.focus() }
  else if (event.key === 'Tab') close()
  else if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
    event.preventDefault()
    if (!open.value) await toggle()
    if (!filtered.value.length) return
    active.value = event.key === 'Home' ? 0 : event.key === 'End' ? filtered.value.length - 1
      : active.value < 0 ? (event.key === 'ArrowDown' ? 0 : filtered.value.length - 1) : (active.value + (event.key === 'ArrowDown' ? 1 : -1) + filtered.value.length) % filtered.value.length
    await nextTick(); menu.value?.querySelector('[data-active=true]')?.scrollIntoView({ block:'nearest' })
  } else if (event.key === 'Enter' && open.value) {
    event.preventDefault()
    const focused = filtered.value.findIndex((_, index) => `${props.inputId}-${index}` === event.target?.id)
    const index = focused >= 0 ? focused : active.value < 0 ? 0 : active.value
    if (filtered.value[index]) pick(filtered.value[index])
  }
}
function outside(event) { if (!root.value?.contains(event.target) && !menu.value?.contains(event.target)) close() }
function scrolled(event) { if (open.value && !menu.value?.contains(event.target)) close() }
watch(search, () => active.value = -1)
watch(() => props.disabled, value => { if (value) close() })
onMounted(() => { document.addEventListener('pointerdown', outside, true); window.addEventListener('resize', close); window.addEventListener('scroll', scrolled, true) })
onBeforeUnmount(() => { document.removeEventListener('pointerdown', outside, true); window.removeEventListener('resize', close); window.removeEventListener('scroll', scrolled, true) })
</script>

<template>
  <div ref="root" class="suite-filter"><button type="button" :disabled="disabled" :aria-label="label" aria-haspopup="listbox" :aria-expanded="open" :aria-controls="inputId" @click="toggle" @keydown="onKey"><span>{{ selected?.label || label }}</span><span aria-hidden="true">⌄</span></button></div>
  <Teleport to="body"><div v-if="open" ref="menu" class="suite-filter-menu" :style="position" @keydown="onKey"><input ref="searchInput" v-model="search" :aria-label="`搜索${label}`" placeholder="搜索…" role="combobox" :aria-expanded="true" :aria-controls="inputId" :aria-activedescendant="active >= 0 ? `${inputId}-${active}` : undefined" /><div :id="inputId" role="listbox" :aria-label="label" class="filter-options"><button v-for="(option, index) in filtered" :id="`${inputId}-${index}`" :key="String(option.value)" type="button" role="option" :aria-selected="String(option.value) === String(modelValue)" :data-active="active === index" @click="pick(option)">{{ option.label }}<span v-if="String(option.value) === String(modelValue)" aria-hidden="true">✓</span></button><p v-if="!filtered.length">没有匹配选项</p></div></div></Teleport>
</template>

<style scoped>
.suite-filter { flex:1; min-width:0; }.suite-filter>button { display:flex; align-items:center; justify-content:space-between; gap:8px; width:100%; height:30px; padding:0 9px; border:1px solid var(--border); border-radius:5px; background:var(--surface); color:var(--text-muted); font:inherit; font-size:11px; cursor:pointer; }.suite-filter>button>span:first-child{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.suite-filter-menu { position:fixed; z-index:180; display:flex;flex-direction:column;gap:7px;padding:8px;border:1px solid var(--border);border-radius:8px;background:var(--surface);box-shadow:var(--shadow-lg);overflow:hidden; }.suite-filter-menu>input { height:30px;flex:none;padding:0 8px;border:1px solid var(--border);border-radius:5px;background:var(--surface-2);color:var(--text);font:inherit;font-size:12px;min-width:0; }.filter-options { overflow:auto;scrollbar-width:none;overscroll-behavior:contain;min-height:0; }.filter-options::-webkit-scrollbar{display:none;width:0;height:0}.filter-options button{display:flex;justify-content:space-between;align-items:center;gap:10px;width:100%;padding:8px;border:0;border-radius:4px;background:transparent;color:var(--text);text-align:left;font:inherit;font-size:12px;overflow-wrap:anywhere;cursor:pointer}.filter-options button:hover,.filter-options button[data-active=true]{background:var(--surface-2)}.filter-options button[aria-selected=true]{color:var(--primary)}.filter-options p{padding:12px;color:var(--text-muted);font-size:12px}button:focus-visible,input:focus-visible{outline:2px solid var(--primary);outline-offset:-2px}
</style>
