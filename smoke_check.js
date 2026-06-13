#!/usr/bin/env node
/*
 * smoke_check.js — guards against init-time crashes reaching production.
 *
 * The black-screen outage was a runtime ReferenceError (renderPath was deleted
 * but still called in init()). A syntax parse can't catch that — you have to
 * actually RUN the script. This loads every inline <script> from index.html and
 * login.html into a stubbed-DOM sandbox and executes it. If the top-level code
 * or init() throws synchronously (e.g. calls an undefined function), this exits
 * non-zero so the bug never ships.
 *
 * Usage:  node smoke_check.js
 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');

// A universal fake DOM node: any property access or method call returns another
// fake (callable + indexable), so arbitrary DOM usage never throws.
function fakeEl() {
  const fn = function () { return fakeEl(); };
  return new Proxy(fn, {
    get(_t, prop) {
      if (prop === Symbol.iterator) return function* () {};
      if (prop === 'length') return 0;
      if (['value', 'textContent', 'innerHTML', 'innerText', 'className', 'id'].includes(prop)) return '';
      if (prop === 'style' || prop === 'classList' || prop === 'dataset' ||
          prop === 'parentElement' || prop === 'closest') return fakeEl();
      return fakeEl();
    },
    set() { return true; },
    apply() { return fakeEl(); },
  });
}

function makeSandbox() {
  const sessionStub = { access_token: 't', user: { id: 'u', email: 'a@b.com' } };
  const supabaseClient = {
    auth: {
      getSession: async () => ({ data: { session: sessionStub } }),
      getUser: async () => ({ data: { user: sessionStub.user } }),
      signOut: async () => ({}),
      signInWithPassword: async () => ({ data: { session: sessionStub }, error: null }),
      signUp: async () => ({ data: { session: sessionStub }, error: null }),
    },
  };
  const documentStub = {
    getElementById: () => fakeEl(),
    querySelector: () => fakeEl(),
    querySelectorAll: () => fakeEl(),
    createElement: () => fakeEl(),
    addEventListener: () => {},
    body: fakeEl(),
  };
  const sandbox = {
    document: documentStub,
    window: {
      supabase: { createClient: () => supabaseClient },
      location: { href: '', replace() {}, search: '' },
      history: { replaceState() {} },
      addEventListener: () => {},
    },
    supabase: { createClient: () => supabaseClient },
    localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
    marked: { parse: (s) => s },
    tailwind: {},               // tailwind CDN global (config block in login.html)
    navigator: { userAgent: 'smoke' },
    fetch: async () => ({ ok: false, json: async () => ({}), text: async () => '' }),
    setTimeout: () => 0,        // don't actually schedule (avoids hanging/animations)
    setInterval: () => 0,       // don't start the heartbeat timer
    clearTimeout: () => {},
    clearInterval: () => {},
    console,
    alert: () => {},
    URLSearchParams,
    Date,
    Math,
    JSON,
  };
  sandbox.window.document = documentStub;
  sandbox.globalThis = sandbox;
  return sandbox;
}

function inlineScripts(html) {
  return [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((m) => m[1]);
}

function check(file) {
  const html = fs.readFileSync(path.join(__dirname, file), 'utf8');
  const scripts = inlineScripts(html);
  if (!scripts.length) { console.log(`  (no inline scripts in ${file})`); return true; }
  let ok = true;
  scripts.forEach((src, i) => {
    const sandbox = makeSandbox();
    vm.createContext(sandbox);
    try {
      new vm.Script(src, { filename: `${file}#script${i}` }).runInContext(sandbox, { timeout: 5000 });
      console.log(`  ✓ ${file} script[${i}] executed without throwing`);
    } catch (e) {
      ok = false;
      console.error(`  ✗ ${file} script[${i}] threw: ${e.name}: ${e.message}`);
    }
  });
  return ok;
}

console.log('Running init-time smoke check…');
const results = ['index.html', 'login.html'].map(check);
if (results.every(Boolean)) {
  console.log('✅ smoke check passed — no init-time crashes.');
  process.exit(0);
} else {
  console.error('❌ smoke check FAILED — an inline script throws at load/init time.');
  process.exit(1);
}
