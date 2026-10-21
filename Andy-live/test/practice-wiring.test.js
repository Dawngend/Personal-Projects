const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const read = file => fs.readFileSync(path.join(__dirname, '..', 'src', file), 'utf8');

test('main.js registers the practice channels and both permission handlers', () => {
    const main = read('main.js');
    assert.match(main, /'practice:transcribe'/);
    assert.match(main, /'practice:feedback'/);
    assert.match(main, /session: electronSession/);
    assert.match(main, /setPermissionRequestHandler/);
    assert.match(main, /setPermissionCheckHandler/);
});

test('main.js still has the original session object', () => {
    assert.match(read('main.js'), /const session = \{/);
});

test('preload.js exposes the practice namespace', () => {
    const preload = read('preload.js');
    assert.match(preload, /practice:\s*\{/);
    assert.match(preload, /'practice:transcribe'/);
    assert.match(preload, /'practice:feedback'/);
});

test('index.html loads only the browser-safe practice scripts', () => {
    const html = read('renderer/index.html');
    for (const file of ['questions', 'select', 'summary', 'recorder']) {
        assert.match(html, new RegExp(`<script src="\\.\\./practice/${file}\\.js"></script>`));
    }
    assert.match(html, /<script src="practice\.js"><\/script>/);
    for (const file of ['service', 'feedback', 'permissions']) {
        assert.doesNotMatch(html, new RegExp(`${file}\\.js`));
    }
});

test('browser-safe practice files do not share a global name', () => {
    const names = ['questions', 'select', 'summary', 'recorder'].map(file => {
        const match = read(`practice/${file}.js`).match(/^const (\w+) =/m);
        assert.ok(match, `${file}.js needs a top-level const`);
        return match[1];
    });
    assert.equal(new Set(names).size, names.length);
    assert.ok(!names.includes('api'));
});
