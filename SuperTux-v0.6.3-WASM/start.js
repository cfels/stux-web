async function start() {
  if (!crossOriginIsolated) {
    if (!('serviceWorker' in navigator)) throw new Error('This browser does not support WASM threads.');
    if (navigator.serviceWorker.controller) throw new Error('WASM threads are unavailable. Try another browser.');
    Module.setStatus('Preparing...');
    navigator.serviceWorker.addEventListener('controllerchange', () => location.reload(), { once: true });
    await navigator.serviceWorker.register('../sw.js');
    await navigator.serviceWorker.ready;
    return;
  }

  const data = new Uint8Array(245929603);
  let offset = 0;
  for (let part = 0; part < 4; part++) {
    const response = await fetch(`supertux2.data.part${part}`);
    if (!response.ok) throw new Error(`Could not load game data (${response.status}).`);
    const reader = response.body.getReader();
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      data.set(value, offset);
      offset += value.length;
      Module.setStatus(`Downloading data... (${offset}/${data.length})`);
    }
  }
  if (offset !== data.length) throw new Error('Incomplete game data.');
  Module.getPreloadedPackage = () => {
    Module.getPreloadedPackage = null;
    return data.buffer;
  };
  const script = document.createElement('script');
  script.src = 'supertux2.js';
  script.onerror = () => Module.setStatus('Could not load SuperTux. Reload to retry.');
  document.body.appendChild(script);
}

start().catch(error => Module.setStatus(error.message));
