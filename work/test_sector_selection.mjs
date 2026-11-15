import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { test } from 'node:test';

test('removing All preserves parent indicator until the industry is cleared', () => {
  const html = readFileSync(new URL('../outputs/index.html', import.meta.url), 'utf8');
  const source = html.slice(html.indexOf('    function renderFilters('), html.indexOf('    class LineChart'));
  const root = { nodes: [], set innerHTML(value) { this.nodes = []; }, appendChild(node) { this.nodes.push(node); } };
  const other = { level: 1, parent: 'Other', name: 'Other' };
  const state = { selections: [other, { level: 1, parent: 'Bank', name: 'Bank' }, { level: 2, parent: 'Bank', name: 'City' }] };
  let context;
  const document = {
    getElementById: () => root,
    createElement: () => {
      const node = { controls: {}, classList: { toggle() {} } };
      Object.defineProperty(node, 'innerHTML', { set(markup) {
        for (const match of markup.matchAll(/<input class="check ([^"]+)"([^>]+)>/g)) {
          node.controls['.' + match[1]] = { checked: /\bchecked\b/.test(match[2]), dataset: { child: /data-child="([^"]+)"/.exec(match[2])?.[1] } };
        }
      } });
      node.querySelector = selector => node.controls[selector] ||= {};
      node.querySelectorAll = () => Object.entries(node.controls).filter(([selector]) => selector === '.child-check').map(([, input]) => input);
      return node;
    }
  };
  context = vm.createContext({ document, state, industries: { Bank: ['City'] }, marketCap: () => 1, formatMarketCap: String, prefetchIndustry() {}, update: () => vm.runInContext('renderFilters()', context) });
  vm.runInContext(source + '\nrenderFilters();', context);
  const control = selector => root.nodes[0].controls[selector];
  assert.equal(control('.parent-check').checked, true);
  assert.equal(control('.all-check').checked, true);
  control('.all-check').onchange({ target: { checked: false } });
  assert.equal(control('.all-check').checked, false);
  assert.equal(control('.child-check').checked, true);
  assert.equal(control('.parent-check').checked, true);
  control('.parent-check').onchange({ target: { checked: false } });
  assert.equal(control('.parent-check').checked, false);
  assert.equal(control('.all-check').checked, false);
  assert.equal(control('.child-check').checked, false);
  assert.deepEqual(Array.from(state.selections), [other]);
});
