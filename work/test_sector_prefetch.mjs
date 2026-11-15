import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { test } from 'node:test';

test('a group downloads once, limits background requests, and retries failures', async () => {
  const html = readFileSync(new URL('../outputs/index.html', import.meta.url), 'utf8');
  const loader = html.slice(html.indexOf('const historyLoads ='), html.indexOf('    async function update()'));
  const calls = [];
  let active = 0;
  let peak = 0;
  let failedOnce = false;
  const metrics = Object.fromEntries(['Group', 'A', 'B', 'Other'].map(name => [name, { latest: {} }]));
  const context = vm.createContext({
    industries: { Group: ['A', 'B'], Other: [] },
    realData: { metrics, historyFiles: Object.fromEntries(Object.keys(metrics).map(name => [name, name])) },
    fetch: async name => {
      calls.push(name);
      active++;
      peak = Math.max(peak, active);
      await new Promise(resolve => setTimeout(resolve, 5));
      active--;
      if (name === 'B' && !failedOnce) {
        failedOnce = true;
        throw new Error('transient failure');
      }
      return { ok: true, json: async () => ({ latest: {}, periods: { '10': { price: [100] } } }) };
    }
  });
  vm.runInContext(loader, context);
  const run = source => vm.runInContext(source, context);
  const waitUntilIdle = async () => {
    for (let i = 0; i < 100; i++) {
      if (run('activePrefetches === 0 && prefetchQueue.length === 0')) return;
      await new Promise(resolve => setTimeout(resolve, 5));
    }
    throw new Error('queue did not settle');
  };
  run('prefetchIndustry("Group"); prefetchIndustry("Group")');
  await run('ensureHistory("A")');
  await waitUntilIdle();
  assert.equal(peak, 2);
  assert.deepEqual(calls.sort(), ['A', 'B', 'Group']);
  assert.equal(metrics.Other.periods, undefined);
  run('prefetchIndustry("Group")');
  await waitUntilIdle();
  assert.ok(metrics.B.periods);
  assert.equal(calls.filter(name => name === 'A').length, 1);
  assert.equal(calls.filter(name => name === 'B').length, 2);
  assert.equal(calls.length, 4);
});
