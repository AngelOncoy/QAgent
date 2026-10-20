// Verificación lógica real de las funciones puras de la issue #66 (sin navegador).
const fs = require('fs');
const ruta = process.argv[2];
const src = fs.readFileSync(ruta, 'utf8');
function registrarComponente() {}
const window = {};
const document = { querySelectorAll: () => [], querySelector: () => null };
function $(id) { return null; }
const factory = new Function(
  'registrarComponente', 'window', 'document', '$', 'MODULES',
  src + '\nreturn {calidadEndpoint, endpointElegible, endpointsIncluidos, moduloConSeleccion, contarEndpointsPorRevisar, totalFuncionesDetectadas, totalEndpointsDetectados};'
);
const MODS = [
  { path: 'a.py', sel: true, fns: [{ n: 'f1', inc: true }], endpoints: [
    { objetivo: 'GET /a', inc: true, response_model: 'A', status_code: 200, status_code_declarado: true },
    { objetivo: 'POST /a', inc: true, response_model: null, status_code: 200, status_code_declarado: false },
    { objetivo: 'GET /b', inc: false, response_model: 'B', status_code: 200, status_code_declarado: false },
    { objetivo: null, inc: false, response_model: null, status_code: 200, status_code_declarado: false }
  ] },
  { path: 'b.py', sel: true, fns: [], endpoints: [
    { objetivo: 'DELETE /c', inc: true, response_model: null, status_code: 204, status_code_declarado: true }
  ] }
];
const api = factory(registrarComponente, window, document, $, MODS);
const txt = c => api.calidadEndpoint(c);
console.log('Calidad de endpoints (se calcula en el frontend, no en el backend)');
console.log('  modelo de respuesta + estado declarado :', txt({ response_model: 'X', status_code_declarado: true }));
console.log('  solo modelo de respuesta               :', txt({ response_model: 'X', status_code_declarado: false }));
console.log('  solo estado declarado                  :', txt({ response_model: null, status_code_declarado: true }));
console.log('  ninguno de los dos                     :', txt({ response_model: null, status_code_declarado: false }));
console.log('  200 por defecto (no declarado)         :', txt({ response_model: 'X', status_code: 200, status_code_declarado: false }));
console.log('');
console.log('Elegibilidad (solo con ruta resuelta se puede probar)');
console.log('  GET /a (resuelto)                      :', api.endpointElegible({ objetivo: 'GET /a' }));
console.log('  sin objetivo (ruta no resuelta)        :', api.endpointElegible({ objetivo: null }));
console.log('');
console.log('Conteos sobre los datos de prueba');
console.log('  funciones detectadas                   :', api.totalFuncionesDetectadas());
console.log('  endpoints detectados                   :', api.totalEndpointsDetectados());
console.log('  endpoints por revisar (archivo a.py)   :', api.contarEndpointsPorRevisar(MODS[0]));
console.log('  endpoints por revisar (archivo b.py)   :', api.contarEndpointsPorRevisar(MODS[1]));
console.log('');
console.log('Inclusión que se envía al backend (solo resueltos e incluidos)');
console.log('  archivo a.py                           :', api.endpointsIncluidos(MODS[0]).map(e => e.objetivo).join(', '));
console.log('  archivo b.py                           :', api.endpointsIncluidos(MODS[1]).map(e => e.objetivo).join(', '));
console.log('  módulo solo con funciones              :', api.moduloConSeleccion({ fns: [{ inc: true }], endpoints: [] }));
console.log('  módulo con endpoint sin ruta           :', api.moduloConSeleccion({ fns: [], endpoints: [{ objetivo: null, inc: true }] }));
