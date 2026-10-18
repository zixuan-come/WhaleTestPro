<script setup>
import { nextTick, onBeforeUnmount, onMounted, onUpdated, ref } from 'vue'
defineProps({ label: { type: String, default: '列表' } })
const viewport = ref(null), content = ref(null), atStart = ref(true), atEnd = ref(true)
let observer
function measure() {
  const element = viewport.value
  if (!element) return
  atStart.value = element.scrollTop <= 1
  atEnd.value = element.scrollTop + element.clientHeight >= element.scrollHeight - 1
}
onMounted(() => {
  if (typeof ResizeObserver !== 'undefined') {
    observer = new ResizeObserver(measure)
    observer.observe(viewport.value); observer.observe(content.value)
  }
  measure()
})
onUpdated(() => nextTick(measure))
onBeforeUnmount(() => observer?.disconnect())
</script>

<template>
  <div class="scroll-area">
    <div ref="viewport" class="scroll-viewport" tabindex="0" role="region" :aria-label="label" @scroll.passive="measure"><div ref="content"><slot /></div></div>
    <div v-if="!atStart" class="scroll-cue top" aria-hidden="true"></div>
    <div v-if="!atEnd" class="scroll-cue bottom" aria-hidden="true"></div>
  </div>
</template>

<style scoped>
.scroll-area { position:relative; flex:1; min-height:0; min-width:0; }
.scroll-viewport { position:absolute; inset:0; overflow:auto; overscroll-behavior:contain; scrollbar-width:none; -ms-overflow-style:none; }
.scroll-viewport::-webkit-scrollbar { display:none; width:0; height:0; }
.scroll-viewport:focus-visible { outline:2px solid var(--primary); outline-offset:-2px; border-radius:5px; }
.scroll-cue { position:absolute; left:0; right:0; height:14px; pointer-events:none; z-index:1; }
.top { top:0; background:linear-gradient(var(--surface),transparent); }
.bottom { bottom:0; background:linear-gradient(transparent,var(--surface)); }
</style>
