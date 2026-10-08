// puente-python.js — recibe los eventos que Python envía a la interfaz (DesktopAPI.emit_event)
window.onPyAgentEvent = function(event) {
  console.log("[Python Event]", event);
  if (event.type === 'log') {
    toast(`Python: ${event.data.message}`);
  } else if (event.type === 'clonado_avance') {
    avanceClonado(event.data);
  } else if (event.type === 'clonado_fin') {
    finClonado(event.data);
  }
};

