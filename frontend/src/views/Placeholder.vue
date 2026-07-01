<script setup>
import { useRoute } from 'vue-router'
import { computed } from 'vue'
const route = useRoute()
const title = computed(() => route.meta.title || '页面')
</script>

<template>
  <div class="placeholder panel">
    <div class="ico">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6">
        <rect x="3" y="3" width="18" height="18" rx="3" />
        <path d="M3 9h18M9 21V9" />
      </svg>
    </div>
    <h2>{{ title }}</h2>
    <p>该模块界面建设中,骨架已就位,接入后端接口后即可上线。</p>
  </div>
</template>

<style scoped>
.placeholder { display:flex; flex-direction:column; align-items:center; justify-content:center;
  padding:80px 24px; text-align:center; }
.ico { width:64px; height:64px; border-radius:18px; display:grid; place-items:center; color:#fff;
  background:linear-gradient(135deg,var(--primary),var(--primary-2)); box-shadow:0 10px 24px var(--ring);
  margin-bottom:20px; }
.ico svg { width:32px; height:32px; }
h2 { font-size:18px; font-weight:750; margin-bottom:8px; }
p { font-size:13px; color:var(--text-muted); max-width:360px; line-height:1.6; }
</style>
