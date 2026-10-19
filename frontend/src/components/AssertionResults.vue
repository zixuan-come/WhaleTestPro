<script setup>
import { describeAssertion, formatAssertionValue } from '../utils/assertionRules'
defineProps({ results: { type: Array, default: () => [] }, rules: { type: Array, default: () => [] } })
</script>
<template>
  <div class="assertion-results" role="region" aria-label="断言执行明细" tabindex="0">
    <table><thead><tr><th scope="col">断言对象</th><th scope="col">字段 / 表达式</th><th scope="col">判断条件</th><th scope="col">期望值</th><th scope="col">实际值</th><th scope="col">结果</th></tr></thead>
      <tbody><tr v-for="(result, index) in results" :key="index">
        <td>{{ describeAssertion(result).target }}</td><td><code>{{ describeAssertion(rules[index] || result).path }}</code></td><td>{{ describeAssertion(result).operator }}</td>
        <td><code>{{ formatAssertionValue(result.expected) }}</code></td><td><code>{{ formatAssertionValue(result.actual) }}</code></td><td><span class="result-badge" :class="result.passed ? 'passed' : 'failed'">{{ result.passed ? '通过' : '失败' }}</span></td>
      </tr></tbody>
    </table>
  </div>
</template>
<style scoped>
.assertion-results{min-width:0;overflow:auto;scrollbar-width:thin;scrollbar-color:var(--border) transparent;border:1px solid var(--border);border-radius:7px}.assertion-results:focus-visible{outline:2px solid var(--primary);outline-offset:2px}
table{width:100%;min-width:540px;table-layout:fixed;border-collapse:collapse;text-align:left;font-size:12px;color:var(--text)}th,td{padding:9px 10px;vertical-align:top;overflow-wrap:anywhere;border-bottom:1px solid var(--border);line-height:1.6}th{font-weight:500;color:var(--text-muted);background:var(--surface-2)}th:first-child{width:15%}th:nth-child(2){width:20%}th:nth-child(3){width:12%}th:last-child{width:64px}tr:last-child td{border-bottom:0}code{white-space:pre-wrap;font:11.5px/1.6 ui-monospace,Consolas,monospace}.result-badge{white-space:nowrap;border-radius:10px;padding:2px 7px;font-size:11px}.passed{color:var(--pass-fg);background:var(--pass-bg)}.failed{color:var(--fail-fg);background:var(--fail-bg)}
</style>
