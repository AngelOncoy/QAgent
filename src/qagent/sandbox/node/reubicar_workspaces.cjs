'use strict';
// Reubica las dependencias de un monorepo para el sandbox de QAgent (#272).
//
// Corre dentro de la imagen derivada, después de instalar (sin scripts del proyecto) en
// la carpeta temporal. Las pruebas se ejecutan con el proyecto montado en /work/proyecto
// y las dependencias en /work/node_modules, así que:
//   1. lo que quedó en <workspace>/node_modules se sube al node_modules de la raíz
//      (si ya hay una versión de ese paquete en la raíz, se deja la de la raíz);
//   2. los enlaces a carpetas del proyecto (los paquetes del propio monorepo) se
//      reescriben para apuntar a /work/proyecto/<ruta>;
//   3. los enlaces dentro de node_modules apuntan a /work/node_modules/<ruta>.
//
// Uso: node reubicar_workspaces.cjs <carpeta de instalación> <node_modules final> <proyecto final>

const fs = require('fs');
const path = require('path');

const [raiz, nmFinal, proyectoFinal] = process.argv.slice(2).map((p) => path.resolve(p));
const nmRaiz = path.join(raiz, 'node_modules');

function existe(ruta) {
  try {
    fs.lstatSync(ruta);
    return true;
  } catch {
    return false;
  }
}

function esEnlace(ruta) {
  try {
    return fs.lstatSync(ruta).isSymbolicLink();
  } catch {
    return false;
  }
}

function dentro(ruta, carpeta) {
  const relativa = path.relative(carpeta, ruta);
  return relativa === '' || (!relativa.startsWith('..') && !path.isAbsolute(relativa));
}

// Destino final de una ruta absoluta de la instalación temporal.
function rutaFinal(destino) {
  if (dentro(destino, nmRaiz)) {
    return path.join(nmFinal, path.relative(nmRaiz, destino));
  }
  if (dentro(destino, raiz)) {
    const relativa = path.relative(raiz, destino);
    if (relativa.split(path.sep).includes('node_modules')) {
      return null; // apunta a un node_modules de workspace que no se conserva
    }
    return path.join(proyectoFinal, relativa);
  }
  return destino;
}

// Paquetes de un node_modules: «nombre» o «@scope/nombre» (sin .bin, .pnpm...).
function paquetes(nm) {
  if (!existe(nm)) return [];
  const lista = [];
  for (const entrada of fs.readdirSync(nm)) {
    if (entrada.startsWith('.')) continue;
    const ruta = path.join(nm, entrada);
    if (entrada.startsWith('@') && !esEnlace(ruta) && fs.statSync(ruta).isDirectory()) {
      for (const interna of fs.readdirSync(ruta)) lista.push(`${entrada}/${interna}`);
    } else {
      lista.push(entrada);
    }
  }
  return lista;
}

// Mueve una entrada; si es un enlace, lo recrea con su destino final (absoluto).
function mover(origen, destino) {
  fs.mkdirSync(path.dirname(destino), { recursive: true });
  if (esEnlace(origen)) {
    const apunta = path.resolve(path.dirname(origen), fs.readlinkSync(origen));
    const final = rutaFinal(apunta);
    fs.unlinkSync(origen);
    if (final) fs.symlinkSync(final, destino);
    return;
  }
  fs.renameSync(origen, destino);
}

// Carpetas de workspaces: las que tienen package.json (solo se copiaron esos).
function workspaces(carpeta, lista = []) {
  for (const entrada of fs.readdirSync(carpeta, { withFileTypes: true })) {
    if (!entrada.isDirectory() || entrada.name === 'node_modules' || entrada.isSymbolicLink()) {
      continue;
    }
    const ruta = path.join(carpeta, entrada.name);
    if (existe(path.join(ruta, 'package.json'))) lista.push(ruta);
    workspaces(ruta, lista);
  }
  return lista;
}

fs.mkdirSync(nmRaiz, { recursive: true });
let sinUbicar = 0;
for (const ws of workspaces(raiz)) {
  const nm = path.join(ws, 'node_modules');
  for (const nombre of paquetes(nm)) {
    const destino = path.join(nmRaiz, nombre);
    if (existe(destino)) {
      sinUbicar += 1;
      continue;
    }
    mover(path.join(nm, nombre), destino);
  }
  const bin = path.join(nm, '.bin');
  if (existe(bin)) {
    for (const nombre of fs.readdirSync(bin)) {
      const destino = path.join(nmRaiz, '.bin', nombre);
      if (!existe(destino)) mover(path.join(bin, nombre), destino);
    }
  }
}

// Enlaces que quedan en la raíz (paquetes del monorepo y binarios): destino final.
const enlaces = [
  ...paquetes(nmRaiz).map((nombre) => path.join(nmRaiz, nombre)),
  ...(existe(path.join(nmRaiz, '.bin'))
    ? fs.readdirSync(path.join(nmRaiz, '.bin')).map((n) => path.join(nmRaiz, '.bin', n))
    : []),
];
let reescritos = 0;
for (const enlace of enlaces) {
  if (!esEnlace(enlace)) continue;
  const apunta = path.resolve(path.dirname(enlace), fs.readlinkSync(enlace));
  if (!dentro(apunta, raiz)) continue;
  const final = rutaFinal(apunta);
  fs.unlinkSync(enlace);
  if (final) {
    fs.symlinkSync(final, enlace);
    reescritos += 1;
  }
}

console.log(`QAGENT: workspaces reubicados (${reescritos} enlace(s) del proyecto).`);
if (sinUbicar > 0) {
  console.log(
    `QAGENT: ${sinUbicar} paquete(s) de workspaces tienen otra versión en la raíz; ` +
      'se usa la de la raíz.',
  );
}
