// configuracion.js — pantalla «Configuración del sistema» (solo lectura): agentes, límites y entorno
// HTML del componente (se monta en el marcador data-componente="configuracion/configuracion" de index.html)
registrarComponente('configuracion/configuracion', `<!-- ===== CONFIGURACIÓN DEL SISTEMA (solo lectura) ===== -->
<section id="s-config" class="hide scroll">
  <div class="page">
    <div class="card"><div class="projhead">
      <span class="t">Configuración del sistema</span>
      <span class="pill p-grey">Solo lectura · definida por el equipo en <span class="mono">config.toml</span></span>
    </div></div>
    <div class="card">
      <h4>Modelo de cada agente <span class="pill p-amber">precios de ejemplo</span></h4>
      <table><thead><tr><th>Agente</th><th>Modelo</th><th>Precio (US$ por millón de tokens)</th><th>Por qué este modelo</th></tr></thead><tbody id="cfgAgents"></tbody></table>
      <div class="hint" style="padding:10px 16px 14px">Los modelos son fijos para que todas las corridas sean comparables. Cada corrida guarda en su registro qué modelos usó.</div>
    </div>
    <div class="grid2" style="grid-template-columns:1fr 1fr">
      <div class="card"><h4>Límites de cada corrida</h4><div class="bd checks" id="cfgLimits"></div></div>
      <div class="card"><h4>Entorno y datos</h4><div class="bd checks">
        <div class="c"><span class="i ok">✓</span><div>Sandbox: contenedor <span class="mono">pyagent-sandbox:base</span>, <b>sin red</b> y sin acceso a los archivos del equipo</div></div>
        <div class="c"><span class="i ok">✓</span><div>Claves de IA: cargadas desde <span class="mono">.env</span> · nunca se muestran, nunca se suben al repositorio y nunca entran al sandbox</div></div>
        <div class="c"><span class="i ok">✓</span><div>Resultados, specs y pruebas guardadas: <span class="mono">&lt;proyecto&gt;/.pyagent/</span></div></div>
        <div class="c"><span class="i ok">✓</span><div>Tipo de cambio para costos: S/ 3.37 por US$ (carta del proyecto)</div></div>
      </div></div>
    </div>
    <div class="card">
      <h4>Cómo cambia esto el equipo</h4>
      <div class="bd"><p class="hint" style="margin:0 0 10px">Se edita <span class="mono">config.toml</span> y se reinicia la aplicación. El usuario no necesita tocar nada.</p>
<pre class="rcode">[agentes.planner]
modelo = "modelo-contexto-amplio"   # ejemplo
precio_usd_por_millon = 5.00

[agentes.generator]
modelo = "modelo-economico"         # ejemplo
precio_usd_por_millon = 0.60

[agentes.reviewer]
modelo = "modelo-economico"         # ejemplo
precio_usd_por_millon = 0.60

[limites]
tope_soles_por_corrida = 5.00
reintentos_max = 3                  # regla del proyecto, no se cambia

# Las claves van en .env (incluido en .gitignore):
# PROVEEDOR_API_KEY=...</pre></div>
    </div>
  </div>
</section>
`);

function renderConfig(){
  $('cfgAgents').innerHTML = ['P','G','R'].map(k => `<tr><td><b style="color:${{P:'var(--blue-300)',G:'var(--purple-300)',R:'var(--green-300)'}[k]}">${AGENTS_CFG[k].name}</b></td><td>${AGENTS_CFG[k].model}</td><td class="mono">US$ ${AGENTS_CFG[k].price.toFixed(2)}</td><td style="font-size:12px;color:var(--mut)">${AGENTS_CFG[k].why}</td></tr>`).join('');
  $('cfgLimits').innerHTML = `
    <div class="c"><span class="i ok">✓</span><div><b>Tope de gasto: S/ ${TOPE_PEN.toFixed(2)} por corrida</b><div class="hint" style="margin:0">La corrida no inicia si el costo estimado lo supera, y se detiene si el gasto real lo alcanza.</div></div></div>
    <div class="c"><span class="i ok">✓</span><div><b>Reintentos: ${MAX_RETRIES} por prueba</b><div class="hint" style="margin:0">Corte anticipado si el mismo error se repite dos veces seguidas.</div></div></div>
    <div class="c"><span class="i ok">✓</span><div><b>Mutation testing: solo en funciones críticas</b><div class="hint" style="margin:0">Nunca sobre el repositorio completo.</div></div></div>
    <div class="c"><span class="i ok">✓</span><div><b>Specs: se reutilizan si la huella del código no cambió</b></div></div>`;
}
