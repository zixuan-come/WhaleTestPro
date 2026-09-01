<script setup>
import { useFeedback } from '../composables/feedback'
const { notice, confirmState, resolveConfirm } = useFeedback()
</script>

<template>
  <Teleport to="body">
    <Transition name="feedback-fade">
      <div v-if="notice" class="feedback-notice" :class="notice.type" role="status" aria-live="polite"><span class="feedback-icon">{{ notice.type === 'success' ? '✓' : '!' }}</span><span>{{ notice.message }}</span></div>
    </Transition>
    <Transition name="feedback-fade">
      <div v-if="confirmState" class="feedback-mask" @click.self="resolveConfirm(false)">
        <div class="feedback-dialog" role="dialog" aria-modal="true" :aria-label="confirmState.title">
          <div class="feedback-dialog-head">{{ confirmState.title }}</div><div class="feedback-dialog-body">{{ confirmState.message }}</div>
          <div class="feedback-dialog-foot"><button class="btn btn-ghost" @click="resolveConfirm(false)">取消</button><button class="btn btn-primary" @click="resolveConfirm(true)">确认</button></div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.feedback-notice { position:fixed; top:50%; left:50%; z-index:300; display:flex; align-items:center; gap:10px; max-width:calc(100vw - 40px); padding:14px 18px; border:1px solid var(--fail-fg); border-radius:10px; background:var(--surface); color:var(--fail-fg); font-size:13px; font-weight:600; box-shadow:var(--shadow-lg); transform:translate(-50%,-50%); }
.feedback-notice.success { border-color:var(--primary); color:var(--primary); }
.feedback-icon { display:grid; place-items:center; width:20px; height:20px; border-radius:50%; background:var(--fail-bg); font-size:12px; font-weight:800; }
.feedback-notice.success .feedback-icon { background:var(--ring); }
.feedback-mask { position:fixed; inset:0; z-index:290; display:grid; place-items:center; padding:20px; background:rgba(15,17,40,.44); }
.feedback-dialog { width:min(420px,100%); background:var(--surface); border:1px solid var(--border); border-radius:14px; box-shadow:var(--shadow-lg); overflow:hidden; }
.feedback-dialog-head { padding:18px 22px; border-bottom:1px solid var(--border); font-size:15px; font-weight:700; }
.feedback-dialog-body { padding:22px; color:var(--text); font-size:13.5px; line-height:1.6; white-space:pre-line; }
.feedback-dialog-foot { display:flex; justify-content:flex-end; gap:10px; padding:14px 22px; border-top:1px solid var(--border); }
.feedback-dialog-foot button { padding:8px 16px; border-radius:8px; border:1px solid var(--border); cursor:pointer; font-size:13px; }
.feedback-dialog-foot .btn-primary { background:var(--primary); color:#fff; border-color:var(--primary); }
.feedback-dialog-foot .btn-ghost { background:var(--surface-2); color:var(--text); }
.feedback-fade-enter-active,.feedback-fade-leave-active { transition:opacity .16s,transform .16s; }
.feedback-fade-enter-from,.feedback-fade-leave-to { opacity:0; transform:scale(.98); }
</style>