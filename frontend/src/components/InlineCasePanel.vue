<script setup>
defineProps({ title: { type: String, default: '' }, busy: Boolean })
</script>

<template>
  <section class="inline-case-panel panel">
    <header class="inline-case-heading"><h2>{{ title }}</h2><slot name="actions" /></header>
    <div class="inline-case-body"><slot /></div>
    <footer v-if="$slots.foot" class="inline-case-footer"><slot name="foot" /></footer>
  </section>
</template>

<style scoped>
.inline-case-panel{min-width:0;overflow:hidden}.inline-case-heading{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;padding:18px 20px;border-bottom:1px solid var(--border)}h2{font-size:17px;margin:0;overflow-wrap:anywhere;min-width:0}.inline-case-body{padding:20px;min-width:0}.inline-case-footer{display:flex;gap:10px;justify-content:flex-end;padding:16px 20px;border-top:1px solid var(--border);flex-wrap:wrap}@media(max-width:640px){.inline-case-body{padding:14px}.inline-case-heading,.inline-case-footer{padding:14px}}
</style>
