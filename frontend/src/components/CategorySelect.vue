<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps({
  modelValue: { type: String, default: '' },
  categories: { type: Array, default: () => [] },
  inputId: { type: String, default: 'interface-category' },
  disabled: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue'])
const root = ref(null), input = ref(null), menu = ref(null)
const open = ref(false), searching = ref(false), composing = ref(false), activeIndex = ref(-1)
const menuStyle = ref({})
const value = computed(() => props.modelValue.trim())
const categories = computed(() => [...new Set(props.categories.map(name => name.trim()).filter(Boolean))])
const query = computed(() => searching.value ? value.value.toLocaleLowerCase() : '')
const filtered = computed(() => categories.value.filter(name => name.toLocaleLowerCase().includes(query.value)))
const canCreate = computed(() => value.value && !categories.value.includes(value.value))
const options = computed(() => [
  ...(!query.value ? [{ value: '', label: '未分类', kind: 'empty' }] : []),
  ...filtered.value.map(name => ({ value: name, label: name, kind: 'existing' })),
  ...(canCreate.value ? [{ value: value.value, label: value.value, kind: 'new' }] : []),
])
const listId = computed(() => props.inputId + '-options')
const optionId = index => props.inputId + '-option-' + index
const selected = option => option.kind !== 'new' && option.value === value.value

function positionMenu() {
  if (!root.value) return
  const rect = root.value.getBoundingClientRect()
  const below = window.innerHeight - rect.bottom - 18
  const above = rect.top - 18
  const upward = below < 180 && above > below
  const width = Math.min(rect.width, window.innerWidth - 24)
  menuStyle.value = {
    width: width + 'px',
    left: Math.max(12, Math.min(rect.left, window.innerWidth - width - 12)) + 'px',
    top: (upward ? rect.top - 6 : rect.bottom + 6) + 'px',
    maxHeight: Math.max(48, Math.min(260, upward ? above : below)) + 'px',
    transform: upward ? 'translateY(-100%)' : undefined,
  }
}
function show() {
  if (props.disabled) return
  searching.value = false
  activeIndex.value = options.value.findIndex(selected)
  positionMenu()
  open.value = true
}
function close() { open.value = false; activeIndex.value = -1 }
function toggle() {
  if (open.value) close()
  else { input.value?.focus(); show() }
}
function onInput(event) {
  emit('update:modelValue', event.target.value)
  searching.value = true
  activeIndex.value = -1
  positionMenu()
  open.value = true
}
function pick(option) {
  if (props.disabled) return
  emit('update:modelValue', option.value)
  close()
  input.value?.focus()
}
async function move(direction) {
  if (!open.value) show()
  const length = options.value.length
  if (!length) return
  activeIndex.value = activeIndex.value < 0
    ? (direction > 0 ? 0 : length - 1)
    : (activeIndex.value + direction + length) % length
  await nextTick()
  menu.value?.querySelector('[data-active="true"]')?.scrollIntoView({ block: 'nearest' })
}
function onKeydown(event) {
  if (props.disabled || composing.value || event.isComposing || event.keyCode === 229 || event.ctrlKey || event.altKey || event.metaKey) return
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault()
    move(event.key === 'ArrowDown' ? 1 : -1)
  } else if (event.key === 'Enter' && open.value) {
    event.preventDefault()
    pick(options.value[activeIndex.value] || { value: value.value })
  } else if (event.key === 'Escape' && open.value) {
    event.preventDefault()
    event.stopPropagation()
    close()
  } else if (event.key === 'Tab') close()
}
function clear() {
  if (props.disabled) return
  emit('update:modelValue', '')
  input.value?.focus()
  show()
}
function onOutside(event) {
  if (!root.value?.contains(event.target) && !menu.value?.contains(event.target)) close()
}
function onBlur() {
  nextTick(() => {
    if (!root.value?.contains(document.activeElement) && !menu.value?.contains(document.activeElement)) close()
  })
}
function onScroll(event) {
  if (open.value && !menu.value?.contains(event.target)) close()
}
function onResize() { if (open.value) positionMenu() }
watch(() => props.disabled, disabled => { if (disabled) close() })
watch([() => props.modelValue, categories], () => { activeIndex.value = -1 })
onMounted(() => {
  document.addEventListener('pointerdown', onOutside, true)
  window.addEventListener('scroll', onScroll, true)
  window.addEventListener('resize', onResize)
})
onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', onOutside, true)
  window.removeEventListener('scroll', onScroll, true)
  window.removeEventListener('resize', onResize)
})
</script>

<template>
  <div ref="root" class="category-select" :class="{ open, disabled }" @focusout="onBlur">
    <svg class="category-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M3 7h6l2-3h10v15H3z" /></svg>
    <input :id="inputId" ref="input" :value="modelValue" type="text" role="combobox" aria-autocomplete="list" aria-haspopup="listbox" :aria-expanded="open" :aria-controls="listId" :aria-activedescendant="open && activeIndex >= 0 ? optionId(activeIndex) : undefined" :disabled="disabled" autocomplete="off" spellcheck="false" placeholder="选择或输入分类，留空为未分类" @focus="show" @click="!open && show()" @input="onInput" @keydown="onKeydown" @compositionstart="composing = true" @compositionend="composing = false" />
    <div class="category-tools"><button v-if="modelValue" type="button" class="category-clear" aria-label="清空分类" :disabled="disabled" @pointerdown.prevent @click="clear"><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="m4 4 8 8M12 4l-8 8" /></svg></button><button type="button" class="category-toggle" :aria-label="open ? '收起分类选项' : '展开分类选项'" :aria-expanded="open" :aria-controls="listId" :disabled="disabled" @pointerdown.prevent @click="toggle"><svg :class="{ rotated: open }" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="m5 8 5 5 5-5" /></svg></button></div>
  </div>
  <Teleport to="body">
    <div v-if="open" :id="listId" ref="menu" class="category-menu" :style="menuStyle" role="listbox" aria-label="接口分类">
      <div v-if="filtered.length" class="category-menu-heading" role="presentation">已有分类 <span>{{ filtered.length }}</span></div>
      <button v-for="(option, index) in options" :id="optionId(index)" :key="option.kind + ':' + option.value" type="button" class="category-option" :class="{ selected: selected(option), 'is-active': activeIndex === index, 'new-category': option.kind === 'new' }" role="option" :aria-selected="selected(option)" :data-active="activeIndex === index ? 'true' : undefined" tabindex="-1" @pointerdown.prevent @pointermove="activeIndex = index" @click="pick(option)">
        <svg v-if="option.kind === 'new'" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="M10 4v12M4 10h12" /></svg>
        <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="M3 7h6l2-3h10v15H3z" /></svg>
        <span class="category-option-copy"><span>{{ option.kind === 'new' ? '使用新分类「' + option.label + '」' : option.label }}</span><small v-if="option.kind === 'new'">保存接口时创建</small><small v-else-if="option.kind === 'empty'">不设置分类</small></span>
        <svg v-if="selected(option)" class="category-check" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="m4 10 4 4 8-8" /></svg>
      </button>
      <div v-if="!categories.length && !value" class="category-empty" role="presentation">暂无已有分类，可直接输入新名称</div>
    </div>
  </Teleport>
</template>

<style scoped>
.category-select{position:relative;display:flex;align-items:center;min-width:0;height:38px;border:1px solid var(--border);border-radius:8px;background:var(--surface-2);transition:border-color .15s,box-shadow .15s}.category-select:hover{border-color:color-mix(in srgb,var(--primary) 55%,var(--border))}.category-select:focus-within,.category-select.open{border-color:var(--primary);box-shadow:0 0 0 3px var(--ring)}.category-icon{width:16px;height:16px;margin-left:12px;flex:none;color:var(--text-muted)}.category-select input{width:100%;min-width:0;height:100%;border:0;outline:0;padding:0 10px;background:transparent;color:var(--text);font:inherit;font-size:13px}.category-select input::placeholder{color:var(--text-muted)}.category-tools{display:flex;align-items:center;gap:2px;padding-right:5px}.category-tools button{display:grid;place-items:center;flex:none;width:27px;height:27px;padding:0;border:0;border-radius:5px;background:transparent;color:var(--text-muted);cursor:pointer}.category-tools button:hover{background:var(--border);color:var(--primary)}.category-clear svg{width:14px;height:14px}.category-toggle svg{width:16px;height:16px;transition:transform .15s}.category-toggle svg.rotated{transform:rotate(180deg)}.category-tools button:focus-visible{outline:2px solid var(--primary);outline-offset:1px}.category-select.disabled{opacity:.6}.category-select.disabled input,.category-select.disabled button{cursor:not-allowed}
.category-menu{position:fixed;z-index:120;box-sizing:border-box;overflow-y:auto;overscroll-behavior:contain;padding:5px;background:var(--surface);border:1px solid var(--border);border-radius:10px;box-shadow:var(--shadow-lg);color:var(--text)}.category-menu-heading{display:flex;justify-content:space-between;align-items:center;padding:7px 9px;font-size:11.5px;color:var(--text-muted)}.category-menu-heading span{font-variant-numeric:tabular-nums}.category-option{display:flex;align-items:center;gap:10px;width:100%;min-height:38px;padding:9px 10px;border:0;border-radius:6px;background:transparent;color:var(--text);font:inherit;font-size:13px;text-align:left;cursor:pointer}.category-option>svg{width:16px;height:16px;flex:none;color:var(--text-muted)}.category-option.is-active,.category-option:hover{background:var(--surface-2)}.category-option.selected{color:var(--primary);background:var(--surface-2)}.category-option.selected>svg,.category-option.new-category>svg{color:var(--primary)}.category-option-copy{display:flex;flex-direction:column;gap:3px;min-width:0;flex:1;overflow-wrap:anywhere}.category-option-copy small{color:var(--text-muted);font-size:11px}.category-check{margin-left:auto}.category-option.new-category{border-top:1px solid var(--border);border-radius:0 0 6px 6px;margin-top:4px;padding-top:12px;color:var(--primary)}.category-empty{padding:12px 10px;color:var(--text-muted);font-size:12px;line-height:1.6}@media(pointer:coarse){.category-option{min-height:44px}.category-tools button{min-width:32px;height:32px}.category-select{height:44px}.category-select input{font-size:16px}}@media(prefers-reduced-motion:reduce){.category-select,.category-toggle svg{transition:none}}
</style>
