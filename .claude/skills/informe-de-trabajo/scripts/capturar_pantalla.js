#!/usr/bin/env node
// Captura una pantalla de una interfaz web después de ejecutar unos pasos, para usar como imagen de prueba.
//
// Uso (abre su propio navegador sin ventana):
//   node capturar_pantalla.js --url file:///C:/proyecto/frontend/index.html --pasos pasos.js --salida img/prueba-2b.png
// Uso (se conecta a una ventana que ya está abierta con depuración remota, p. ej. una app de escritorio):
//   node capturar_pantalla.js --puerto 9411 --pasos pasos.js --salida img/prueba-3b.png
//
// Opciones:
//   --url       página a abrir (file:// o http://). Se ignora si se usa --puerto
//   --puerto    puerto de depuración remota de una ventana ya abierta
//   --pasos     archivo .js con el CUERPO de una función async que se ejecuta dentro de la página (admite await);
//               opcional. Ejemplo:  await new Promise(r => setTimeout(r, 500)); go('report');
//   --salida    PNG de destino (obligatorio)
//   --ancho / --alto   tamaño de la ventana (por defecto 1400x900)
//   --espera    milisegundos a esperar tras cargar, antes de los pasos (por defecto 1200)
//
// Requiere Node 22+ (usa fetch y WebSocket integrados) y Microsoft Edge o Chrome. Los mismos pasos sobre una
// versión anterior y una nueva dan capturas comparables: úsalo para "antes / después".
const { spawn } = require('child_process');
const fs = require('fs'), os = require('os'), path = require('path');

function argumentos() {
  const a = process.argv.slice(2), o = {};
  for (let i = 0; i < a.length; i += 2) o[a[i].replace(/^--/, '')] = a[i + 1];
  return o;
}
function buscarNavegador() {
  return [process.env.NAVEGADOR,
    'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe', 'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
    'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe', 'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
    '/usr/bin/google-chrome', '/usr/bin/chromium', '/usr/bin/chromium-browser', '/usr/bin/microsoft-edge']
    .filter(Boolean).find(p => fs.existsSync(p));
}
const esperar = ms => new Promise(r => setTimeout(r, ms));
const o = argumentos();
if (!o.salida || (!o.url && !o.puerto)) { console.error('Faltan --salida y --url o --puerto (ver el encabezado del script).'); process.exit(2); }

(async () => {
  let navegador = null, puerto = o.puerto;
  if (!puerto) {
    const exe = buscarNavegador();
    if (!exe) throw new Error('No encontré Edge ni Chrome (define NAVEGADOR con la ruta del ejecutable).');
    puerto = 9300 + Math.floor(Math.random() * 500);
    const perfil = fs.mkdtempSync(path.join(os.tmpdir(), 'captura-'));
    navegador = spawn(exe, ['--headless=new', '--disable-gpu', '--hide-scrollbars', `--remote-debugging-port=${puerto}`, `--user-data-dir=${perfil}`,
      `--window-size=${o.ancho || 1400},${o.alto || 900}`, 'about:blank'], { stdio: 'ignore' });
  }
  try {
    let objetivo;
    for (let i = 0; i < 60 && !objetivo; i++) { await esperar(250); try { objetivo = (await (await fetch(`http://127.0.0.1:${puerto}/json`)).json()).find(t => t.type === 'page'); } catch {} }
    if (!objetivo) throw new Error('No encontré la ventana en el puerto ' + puerto);
    const ws = new WebSocket(objetivo.webSocketDebuggerUrl);
    await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
    let id = 0; const pend = new Map(); const eventos = [];
    ws.onmessage = e => { const m = JSON.parse(e.data); if (m.id && pend.has(m.id)) { pend.get(m.id)(m); pend.delete(m.id); } else eventos.push(m); };
    const enviar = (method, params = {}) => new Promise(r => { const i = ++id; pend.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });

    if (o.url) {
      await enviar('Page.enable'); await enviar('Page.navigate', { url: o.url });
      for (let i = 0; i < 100 && !eventos.some(e => e.method === 'Page.loadEventFired'); i++) await esperar(150);
    }
    await esperar(Number(o.espera || 1200));
    if (o.pasos) {
      const cuerpo = fs.existsSync(o.pasos) ? fs.readFileSync(o.pasos, 'utf8') : o.pasos;
      const r = await enviar('Runtime.evaluate', { expression: `(async () => { ${cuerpo}\n return 'ok'; })()`, awaitPromise: true, returnByValue: true, timeout: 90000 });
      if (r.result.exceptionDetails) throw new Error('Falló un paso dentro de la página: ' + JSON.stringify(r.result.exceptionDetails).slice(0, 400));
    }
    const c = await enviar('Page.captureScreenshot', { format: 'png' });
    fs.mkdirSync(path.dirname(path.resolve(o.salida)), { recursive: true });
    fs.writeFileSync(o.salida, Buffer.from(c.result.data, 'base64'));
    console.log('captura creada:', o.salida);
    ws.close();
  } finally { if (navegador) navegador.kill(); }
})().catch(e => { console.error('ERROR ' + e.message); process.exit(1); });
