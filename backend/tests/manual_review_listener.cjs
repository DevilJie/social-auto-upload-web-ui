// Exercise the actual page listener without a browser or social media account.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync(path.join(__dirname, '../impl/_manual_review.py'), 'utf8');
const script = source.match(/_INSTALL_REVIEW = r"""([\s\S]*?)"""/)[1];
const listeners = {};
let submitted = 0;
const context = {
  window: { signal: () => submitted++ },
  document: {
    addEventListener: (name, listener) => { listeners[name] = listener; },
    createElement: () => ({ dataset: {}, style: {} }),
    body: { appendChild: () => {} },
  },
};
vm.runInNewContext(`(${script})`, context)({ binding: 'signal' });
function send(text, { trusted = true, button = true, tag = 'BUTTON', key, id = '' } = {}) {
  const el = {
    tagName: tag, innerText: text,
    matches: selector => selector === '.xhs-publish-btn' ? false : selector === '#done-button' ? id === 'done-button' : button,
  };
  const event = { isTrusted: trusted, type: key ? 'keydown' : 'click', key, composedPath: () => [el] };
  listeners[event.type](event);
}
send('发布', { trusted: false });
send('发布', { button: false, tag: 'DIV' });
send('保存草稿');
send('发布', { key: 'Tab' });
assert.equal(submitted, 0);
send('发布');
send('立即投稿');
send('发表', { key: 'Enter' });
send('', { button: false, tag: 'XHS-PUBLISH-BTN' });
assert.equal(submitted, 4);
send('Done', { id: 'done-button' });
assert.equal(submitted, 5);
console.log('Manual-review listener: 9 gesture checks passed.');
