const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function browser(script, responses) {
    const nodes = new Map();
    function node(id) {
        if (!nodes.has(id)) nodes.set(id, { innerHTML: '', textContent: '', value: '', style: {}, dataset: {}, listeners: {},
            classList: { add() {}, remove() {}, toggle() {} }, addEventListener(type, fn) { this.listeners[type] = fn; }, appendChild() {} });
        return nodes.get(id);
    }
    node('uploadConfig').textContent = JSON.stringify({ MAX_FILE_SIZE: 4000000, MAX_BATCH_SIZE: 50 });
    const calls = [];
    const context = { window: {}, document: { getElementById: node, querySelectorAll: () => [], querySelector: node, addEventListener() {}, createElement: node },
        fetch: async (url, options) => { calls.push([url, options]); return {ok: true, status: 200, json: async () => responses[url] || {success: true}}; },
        setInterval() {}, clearInterval() {}, setTimeout() {}, clearTimeout() {}, requestAnimationFrame() {}, URL, console, FormData, File };
    vm.createContext(context);
    vm.runInContext(fs.readFileSync('src/static/js/safety.js', 'utf8'), context);
    vm.runInContext(fs.readFileSync(`src/static/js/${script}.js`, 'utf8'), context);
    return { nodes, calls, context };
}
const settle = () => new Promise(resolve => setImmediate(resolve));

test('document metadata and prototype-like folders render safely', async () => {
    const attack = '\"><img src=x onerror=alert(1)>';
    const { nodes } = browser('app', {'/usage': {success: true, data: {used: 0, limit: 0}}, '/files': {success: true, files: [
        { filename: attack, folder: '__proto__', summary: attack, date: attack, tags: [attack] },
        { filename: 'second.txt', folder: attack, tags: 'malformed legacy value' }
    ]}});
    await settle();
    assert.ok(!nodes.get('flatView').innerHTML.includes('<img'));
    assert.ok(nodes.get('flatView').innerHTML.includes('&lt;img'));
    assert.ok(nodes.get('aiView').innerHTML.includes('__proto__'));
    assert.ok(!nodes.get('aiView').innerHTML.includes('<img'));
    assert.equal(nodes.get('meterText').innerText, '100%');
});

test('admin escapes feedback, telemetry, metadata and rejects script URLs', async () => {
    const attack = `'"><img src=x onerror=alert(1)>`;
    const { nodes } = browser('admin', {'/admin/api/data': {success: true,
        users: {[attack]: {metadata: {ip: attack, os: attack}, used: 1, custom_limit: 2}},
        telemetry: [{timestamp: 1, device_id: attack, event: attack, details: {attack}}],
        feedback: [{timestamp: 1, message: attack, image_data: attack, metadata: {current_url: 'javascript:alert(1)', ip: attack}}]
    }});
    await settle();
    for (const id of ['userTable', 'logView', 'feedbackContainer']) {
        assert.ok(!nodes.get(id).innerHTML.includes('<img src=x'), id);
        assert.ok(nodes.get(id).innerHTML.includes('&lt;'), id);
    }
    assert.ok(nodes.get('feedbackContainer').innerHTML.includes('href="#"'));
    assert.ok(!nodes.get('userTable').innerHTML.includes("execAction('"));
});

test('uploads run sequentially with request protection and complete status', async () => {
    const { nodes, calls } = browser('app', {'/upload': {success: true, batch_id: 'job'}, '/status/job': {success: true, data: {status: 'completed', files: {'file.txt': 'DONE'}}}});
    await settle();
    nodes.get('fileInput').listeners.change({target: {files: [new File(['one'], 'one.txt'), new File(['two'], 'two.txt')], value: ''}});
    await settle();
    assert.deepEqual(calls.filter(([url]) => url === '/upload' || url === '/status/job').map(([url]) => url), ['/upload', '/status/job', '/upload', '/status/job']);
    for (const [, options] of calls.filter(([url]) => url === '/upload')) assert.equal(options.headers['X-Unlost-Request'], '1');
    assert.equal(nodes.get('uploadPhaseText').innerText, 'Completed!');
});
