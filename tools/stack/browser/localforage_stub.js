// In-memory stand-in for localforage (promise API; the page keeps only session snapshots in it).
(function () {
  const store = new Map();
  const api = {
    config() { return true; },
    createInstance() { return api; },
    getItem: k => Promise.resolve(store.has(k) ? store.get(k) : null),
    setItem: (k, v) => { store.set(k, v); return Promise.resolve(v); },
    removeItem: k => { store.delete(k); return Promise.resolve(); },
    clear: () => { store.clear(); return Promise.resolve(); },
    keys: () => Promise.resolve([...store.keys()]),
    length: () => Promise.resolve(store.size),
    ready: () => Promise.resolve()
  };
  window.localforage = api;
})();
