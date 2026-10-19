<script setup>
import { formatExtractValue } from '../utils/extractRules'
defineProps({ variables: { type: Object, default: () => ({}) } })
</script>

<template>
  <div class="extracted-variables">
    <table v-if="Object.keys(variables).length"><thead><tr><th scope="col">变量名</th><th scope="col">提取结果</th></tr></thead><tbody><tr v-for="(value, name) in variables" :key="name"><th scope="row"><code>{{ name }}</code></th><td><code>{{ formatExtractValue(value) }}</code></td></tr></tbody></table>
    <p v-else>暂无提取变量</p>
  </div>
</template>

<style scoped>
.extracted-variables{min-width:0;max-height:280px;overflow:auto;scrollbar-width:thin;scrollbar-color:var(--border) transparent}
table{width:100%;table-layout:fixed;border-collapse:collapse;text-align:left;font-size:12px}th,td{padding:9px 10px;vertical-align:top;border-bottom:1px solid var(--border);overflow-wrap:anywhere}thead th{color:var(--text-muted);font-weight:500;background:var(--surface-2)}th:first-child{width:32%}tbody th{font-weight:500}code{font:12px/1.6 ui-monospace,Consolas,monospace;white-space:pre-wrap;color:var(--text)}p{margin:0;padding:10px;color:var(--text-muted);font-size:12px}tr:last-child>*{border-bottom:0}
</style>
