<script setup>
// 全局弹层外壳:统一 mask/modal/head/body/foot 结构与样式。
// 用法:<Modal :title="..." :max-width="560" :busy="saving" @close="close">正文<template #foot>按钮</template></Modal>
// - title:标题文案(需要更复杂的标题可用 #title 具名插槽覆盖)
// - maxWidth:弹层最大宽度(不同页面 520~680 不等)
// - busy:为 true 时(如保存中)点遮罩/关闭按钮不生效,防误关
const props = defineProps({
  title: { type: String, default: '' },
  maxWidth: { type: Number, default: 560 },
  busy: { type: Boolean, default: false },
})
const emit = defineEmits(['close'])

function onClose() {
  if (props.busy) return
  emit('close')
}
</script>

<template>
  <Teleport to="body">
    <div class="mask" @click.self="onClose">
      <div class="modal" :style="{ maxWidth: maxWidth + 'px' }">
        <div class="modal-head">
          <slot name="title">{{ title }}</slot>
          <button class="x" @click="onClose">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 6l12 12M18 6L6 18" /></svg>
          </button>
        </div>
        <div class="modal-body"><slot /></div>
        <div v-if="$slots.foot" class="modal-foot"><slot name="foot" /></div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.mask { position:fixed; inset:0; background:rgba(15,17,40,.44); display:grid; place-items:center;
  padding:20px; z-index:100; }
.modal { width:100%; background:var(--surface); border:1px solid var(--border);
  border-radius:16px; box-shadow:var(--shadow-lg); display:flex; flex-direction:column;
  max-height:88vh; overflow:hidden; }
.modal-head { display:flex; align-items:center; justify-content:space-between; padding:18px 22px;
  border-bottom:1px solid var(--border); font-size:15px; font-weight:700; }
.modal-head .x { background:none; border:none; color:var(--text-muted); cursor:pointer;
  width:30px; height:30px; border-radius:6px; display:grid; place-items:center; transition:background .15s; }
.modal-head .x svg { width:18px; height:18px; }
.modal-head .x:hover { background:var(--surface-2); color:var(--text); }
.modal-body { padding:20px 22px; overflow:auto; }
.modal-foot { display:flex; justify-content:flex-end; gap:10px; padding:16px 22px; border-top:1px solid var(--border); }
</style>
