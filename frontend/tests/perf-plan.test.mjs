import test from 'node:test'
import assert from 'node:assert/strict'
import { newPerfStep, scenarioSteps, buildPerfPlan } from '../src/utils/perf-plan.js'

const form = { mode: 'single', variables: '{"token":"synthetic"}', datasets: '[]', stop_on_failure: true, wait_seconds: 1, timeout_seconds: 30 }
test('interface import keeps method, headers, params and JSON body', () => {
  const step = newPerfStep({ name: 'order', method: 'POST', url: '/orders', headers: { Authorization: '${token}' }, params: { x: 1 }, body: { sku: 2 } })
  const plan = buildPerfPlan(form, [step])
  assert.equal(plan.steps[0].method, 'POST')
  assert.deepEqual(plan.steps[0].body, { sku: 2 })
  assert.deepEqual(plan.steps[0].headers, { Authorization: '${token}' })
})
test('scenario order, duplicates, expected status, extraction and assertions are preserved', () => {
  const cases = [{ id: 1, interface_id: 2, name: 'login', expected_status: 200, extract_rules: { token: '$.token' }, assertions: [] }]
  const steps = scenarioSteps({ case_ids: [1, 1] }, cases, [{ id: 2, method: 'POST', url: '/login' }])
  assert.equal(steps.length, 2)
  assert.deepEqual(steps[1].extract_rules, [{name:'token', path:'$.token'}])
  assert.equal(buildPerfPlan({ ...form, mode: 'chain' }, steps).steps[1].expected_status, 200)
})
test('broken or SQL scenarios are not silently downgraded', () => {
  assert.throws(() => scenarioSteps({ case_ids: [999] }, [], []), /不可访问/)
  assert.throws(() => scenarioSteps({ case_ids: [1] }, [{ id: 1, interface_id: 2, setup_sql: ['DELETE FROM x'] }], [{ id: 2 }]), /SQL/)
})
test('malformed JSON and wrong shapes block saving', () => {
  assert.throws(() => buildPerfPlan(form, [{ ...newPerfStep(), params: '[]' }]), /对象/)
  assert.throws(() => buildPerfPlan({ ...form, variables: 'invalid' }, [newPerfStep()]), /合法 JSON/)
  assert.throws(() => buildPerfPlan(form, [newPerfStep(), newPerfStep()]), /数量/)
})
test('raw body does not undergo JSON parsing and no-body does not send stale text', () => {
  assert.equal(buildPerfPlan(form, [{ ...newPerfStep(), body_type: 'raw', body: '<xml/>' }]).steps[0].body, '<xml/>')
  assert.equal(buildPerfPlan(form, [{ ...newPerfStep(), body: 'stale' }]).steps[0].body, null)
})
