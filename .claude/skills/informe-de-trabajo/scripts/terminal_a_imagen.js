#!/usr/bin/env node
// Convierte la salida REAL de un comando en una imagen con aspecto de terminal.
//
// Uso:
//   <comando> > salida.txt 2>&1
//   node terminal_a_imagen.js --entrada salida.txt --salida img/prueba-1.png \
//        --titulo "python test.py" --reemplazar "C:\Users\Ana\proyecto\.venv\Scripts\python.exe=>python"
//
// Opciones:
//   --entrada      archivo de texto con la salida del comando (obligatorio)
//   --salida       PNG de destino (obligatorio)
//   --titulo       línea que se muestra como comando ejecutado (opcional)
//   --reemplazar   "texto=>reemplazo"; se puede repetir. Sirve para ocultar rutas personales sin tocar el resto
//   --ancho        ancho de la imagen en píxeles (por defecto 1050)
//
// Requiere Node 18+ y Microsoft Edge, Chrome o Chromium instalado. No modifica la salida más que lo pedido
// con --reemplazar: la imagen debe reflejar lo que el comando devolvió de verdad.
const fs = require('fs'), path = require('path'), os = require('os');
const { spawnSync } = require('child_process');

function argumentos() {
  const a = process.argv.slice(2), o = { reemplazar: [] };
  for (let i = 0; i < a.length; i += 2) {
    const k = a[i].replace(/^--/, ''), v = a[i + 1];
    if (k === 'reemplazar') o.reemplazar.push(v); else o[k] = v;
  }
  return o;
}

function buscarNavegador() {
  const candidatos = [
    process.env.NAVEGADOR,
    'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
    'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
    'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
    '/usr/bin/google-chrome', '/usr/bin/chromium', '/usr/bin/chromium-browser', '/usr/bin/microsoft-edge',
  ].filter(Boolean);
  return candidatos.find(p => fs.existsSync(p));
}

const o = argumentos();
if (!o.entrada || !o.salida) { console.error('Faltan --entrada y/o --salida (ver el encabezado del script).'); process.exit(2); }

let texto = fs.readFileSync(o.entrada, 'utf8').replace(/\r/g, '').trim();
for (const par of o.reemplazar) {
  const [de, a] = par.split('=>');
  if (de) texto = texto.split(de).join(a ?? '');
}
const esc = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;');
const ancho = Number(o.ancho || 1050);
const cuerpo = esc(texto).replace(/(All checks passed!|\b\d+ passed\b[^\n]*|\bOK\b[^\n]*)/g, '<b style="color:#7ee787">$1</b>')
                         .replace(/(\bFAILED\b[^\n]*|\bFALL[ÓO]\b[^\n]*|\d+ failed[^\n]*|\bError\b[^\n]*)/g, '<b style="color:#ff7b72">$1</b>');
const titulo = o.titulo ? `<div style="color:#7ee787;margin-bottom:8px">&gt; ${esc(o.titulo)}</div>` : '';
const html = `<body style="margin:0;background:#0c0c0c"><div style="font:15px/1.45 Consolas,'Cascadia Mono',monospace;color:#cccccc;padding:18px 22px;width:${ancho - 50}px">${titulo}<pre style="margin:0;white-space:pre-wrap;word-break:break-word">${cuerpo}</pre></div></body>`;

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'terminal-'));
const archivoHtml = path.join(tmp, 'terminal.html');
fs.writeFileSync(archivoHtml, html);

const navegador = buscarNavegador();
if (!navegador) {
  console.error('No encontré Edge ni Chrome. HTML generado en ' + archivoHtml + ': ábrelo y haz una captura, o define NAVEGADOR con la ruta del ejecutable.');
  process.exit(3);
}
const lineas = texto.split('\n').length + (o.titulo ? 2 : 0);
const alto = Math.max(160, Math.round(lineas * 22 + 60));
fs.mkdirSync(path.dirname(path.resolve(o.salida)), { recursive: true });
const r = spawnSync(navegador, ['--headless=new', '--disable-gpu', '--hide-scrollbars', `--user-data-dir=${path.join(tmp, 'perfil')}`,
  `--window-size=${ancho},${alto}`, `--screenshot=${path.resolve(o.salida)}`, 'file:///' + archivoHtml.replace(/\\/g, '/')], { stdio: 'ignore' });
if (!fs.existsSync(o.salida)) { console.error('El navegador no generó la imagen (código ' + r.status + ').'); process.exit(4); }
console.log('imagen creada:', o.salida, `(${lineas} líneas, ${ancho}x${alto})`);
