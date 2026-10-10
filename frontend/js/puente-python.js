// puente-python.js — recibe los eventos que Python envía a la interfaz (DesktopAPI.emit_event)
window.onPyAgentEvent = function(event) {
  console.log("[Python Event]", event);
  if (event.type === 'log') {
    toast(`Python: ${escHtml(event.data.message)}`);
  } else if (event.type === 'clonado_avance') {
    avanceClonado(event.data);
  } else if (event.type === 'clonado_fin') {
    finClonado(event.data);
  } else if (event.type === 'corrida_evento') {
    monitorEventoReal(event.data);   // una fila del Monitor (monitor.js)
  } else if (event.type === 'corrida_fin') {
    monitorFinReal(event.data);      // resumen de la corrida real (monitor.js)
  }
};

