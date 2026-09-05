<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

const props = defineProps({
  modelValue: { type: [String, Number], default: '' },
  environments: { type: Array, default: () => [] },
  placeholder: { type: String, default: '不指定环境' },
  title: { type: String, default: '选择环境' },
})
const emit = defineEmits(['update:modelValue', 'change'])
const open = ref(false)
const root = ref(null)
const selected = computed(() => props.environments.find(e => String(e.id) === String(props.modelValue)))

function pick(value) {
  emit('update:modelValue', value)
  emit('change', value)
  open.value = false
}
function onOutside(event) {
  if (root.value && !root.value.contains(event.target)) open.value = false
}
onMounted(() => document.addEventListener('click', onOutside))
onBeforeUnmount(() => document.removeEventListener('click', onOutside))
</script>

<template>
  <div ref="root" class="env-select" :class="{ open }">
    <button type="button" class="env-trigger" :title="title" @click.stop="open = !open">
      <span class="env-icon">⌁</span>
      <span class="env-copy">
        <span class="env-label">{{ selected ? selected.name : placeholder }}</span>
        <span v-if="selected?.base_url" class="env-url">{{ selected.base_url }}</span>
      </span>
      <svg class="env-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m6 9 6 6 6-6" /></svg>
    </button>
    <div v-if="open" class="env-menu">
      <button type="button" class="env-option" :class="{ active: !props.modelValue }" @click="pick('')">
        <span class="env-dot muted"></span><span><strong>{{ placeholder }}</strong><small>不使用环境配置</small></span>
      </button>
      <button v-for="environment in environments" :key="environment.id" type="button" class="env-option" :class="{ active: String(environment.id) === String(props.modelValue) }" @click="pick(environment.id)">
        <span class="env-dot"></span><span><strong>{{ environment.name }}</strong><small>{{ environment.base_url || '未配置 Base URL' }}</small></span>
        <svg v-if="String(environment.id) === String(props.modelValue)" class="env-check" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="m5 12 4 4L19 6" /></svg>
      </button>
      <div v-if="!environments.length" class="env-empty">还没有可用环境</div>
    </div>
  </div>
</template>

<style scoped>
.env-select { position:relative; min-width:190px; }
.env-trigger { width:100%; min-height:38px; display:flex; align-items:center; gap:9px; padding:6px 10px; border:1px solid var(--border); border-radius:9px; background:var(--surface-2); color:var(--text); cursor:pointer; text-align:left; transition:border-color .18s, box-shadow .18s, background .18s; }
.env-trigger:hover, .env-select.open .env-trigger { border-color:var(--primary); box-shadow:0 0 0 3px color-mix(in srgb, var(--primary) 14%, transparent); background:var(--surface); }
.env-icon { width:22px; height:22px; display:grid; place-items:center; border-radius:7px; color:var(--primary); background:color-mix(in srgb, var(--primary) 15%, transparent); font-size:17px; line-height:1; }
.env-copy { min-width:0; flex:1; display:flex; flex-direction:column; gap:2px; }
.env-label { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:12.5px; font-weight:650; }
.env-url { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color:var(--text-muted); font-size:10.5px; }
.env-chevron { width:15px; height:15px; flex:none; color:var(--text-muted); transition:transform .18s; }
.env-select.open .env-chevron { transform:rotate(180deg); color:var(--primary); }
.env-menu { position:absolute; z-index:20; top:calc(100% + 7px); left:0; right:0; min-width:260px; padding:6px; border:1px solid var(--border); border-radius:11px; background:var(--surface); box-shadow:var(--shadow-md); animation:env-pop .16s ease-out; }
.env-option { width:100%; display:flex; align-items:center; gap:9px; padding:9px 10px; border:0; border-radius:8px; background:transparent; color:var(--text); text-align:left; cursor:pointer; }
.env-option:hover, .env-option.active { background:var(--surface-2); }
.env-option strong, .env-option small { display:block; }
.env-option strong { font-size:12px; font-weight:650; }
.env-option small { max-width:205px; margin-top:3px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color:var(--text-muted); font-size:10.5px; }
.env-dot { width:8px; height:8px; flex:none; border-radius:50%; background:var(--pass-fg); box-shadow:0 0 0 3px color-mix(in srgb, var(--pass-fg) 15%, transparent); }
.env-dot.muted { background:var(--text-muted); box-shadow:none; }
.env-check { width:15px; height:15px; margin-left:auto; color:var(--primary); }
.env-empty { padding:13px 10px; color:var(--text-muted); font-size:11px; text-align:center; }
@keyframes env-pop { from { opacity:0; transform:translateY(-4px); } to { opacity:1; transform:translateY(0); } }
@media (max-width:600px) { .env-select { min-width:0; width:100%; } .env-menu { min-width:0; } }
</style>
