import fs from 'node:fs';
import path from 'node:path';
import net from 'node:net';
import { spawn } from 'node:child_process';
import { chromium } from 'playwright';

const plan = JSON.parse(fs.readFileSync('/work/tests/plan.json', 'utf8'));
const out = '/out';
const screenshots = path.join(out, 'capturas');
fs.mkdirSync(screenshots, { recursive: true });
const startup = [];
const startedAt = Date.now();
let server;

const clean = value => String(value ?? '').replace(/[\u0000-\u001f]/g, ' ').slice(0, 4000);
const slug = value => value.replace(/[^a-zA-Z0-9_-]+/g, '-').replace(/^-|-$/g, '') || 'raiz';
const allowedHost = host => host === '127.0.0.1' || host === 'localhost' || host === '::1';

async function waitForPort(port, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const ok = await new Promise(resolve => {
      const socket = net.createConnection({ host: '127.0.0.1', port });
      socket.setTimeout(300);
      socket.once('connect', () => { socket.destroy(); resolve(true); });
      socket.once('error', () => resolve(false));
      socket.once('timeout', () => { socket.destroy(); resolve(false); });
    });
    if (ok) return true;
    if (server.exitCode !== null) return false;
    await new Promise(resolve => setTimeout(resolve, 150));
  }
  return false;
}

function stopServer() {
  if (!server || server.exitCode !== null) return;
  try { server.kill('SIGTERM'); } catch {}
}

async function main() {
  server = spawn(plan.start_command[0], plan.start_command.slice(1), {
    cwd: '/work/proyecto',
    env: { PATH: process.env.PATH, HOME: '/tmp', NODE_ENV: 'test',
      HOST: '127.0.0.1', PORT: String(plan.port), ...plan.environment },
    stdio: ['ignore', 'pipe', 'pipe'], detached: false,
  });
  server.stdout.on('data', chunk => startup.push(clean(chunk)));
  server.stderr.on('data', chunk => startup.push(clean(chunk)));
  const ready = await waitForPort(plan.port, plan.startup_timeout_ms);
  if (!ready) {
    return {
      version: '1', status: 'sin_veredicto', startup: {
        ready: false, exit_code: server.exitCode, port: plan.port,
        timeout_ms: plan.startup_timeout_ms, log: startup.join('').slice(-12000),
        reason: server.exitCode === null ? 'La aplicación no respondió antes del límite.' : 'La aplicación terminó antes de estar disponible.'
      }, routes: [], duration_s: (Date.now() - startedAt) / 1000,
    };
  }

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ serviceWorkers: 'block' });
  await context.route('**/*', async route => {
    let url;
    try { url = new URL(route.request().url()); } catch { return route.abort('blockedbyclient'); }
    if ((url.protocol === 'http:' || url.protocol === 'https:') && allowedHost(url.hostname) && Number(url.port || 80) === plan.port) {
      return route.continue();
    }
    return route.abort('blockedbyclient');
  });
  const results = [];
  for (const candidate of plan.routes) {
    if (!candidate.eligible) {
      results.push({ path: candidate.path, status: 'sin_veredicto', http_status: null,
        final_url: null, console_errors: [], page_errors: [], request_errors: [],
        visible_content: false, screenshot: null, duration_ms: 0, reason: candidate.reason });
      continue;
    }
    const page = await context.newPage();
    const consoleErrors = [], pageErrors = [], requestErrors = [];
    page.on('console', msg => { if (msg.type() === 'error') consoleErrors.push(clean(msg.text())); });
    page.on('pageerror', error => pageErrors.push(clean(error.message)));
    page.on('requestfailed', request => requestErrors.push(clean(`${request.url()} · ${request.failure()?.errorText || 'falló'}`)));
    const routeStart = Date.now();
    let response = null, navigationError = null, finalUrl = null, visible = false;
    try {
      response = await page.goto(`http://127.0.0.1:${plan.port}${candidate.path}`, {
        waitUntil: 'domcontentloaded', timeout: plan.route_timeout_ms,
      });
      await page.waitForTimeout(plan.settle_ms);
      finalUrl = page.url();
      const parsed = new URL(finalUrl);
      if (!allowedHost(parsed.hostname) || Number(parsed.port || 80) !== plan.port) navigationError = 'Redirección fuera del origen local autorizado.';
      visible = await page.locator('body').evaluate(body => {
        const text = (body.innerText || '').trim();
        const elements = [...body.querySelectorAll('*')].filter(el => {
          const style = getComputedStyle(el), box = el.getBoundingClientRect();
          return style.visibility !== 'hidden' && style.display !== 'none' && box.width > 0 && box.height > 0;
        });
        return text.length > 0 || elements.some(el => ['IMG','SVG','CANVAS','VIDEO'].includes(el.tagName));
      });
    } catch (error) { navigationError = clean(error.message); }
    const statusCode = response ? response.status() : null;
    const failed = Boolean(navigationError) || statusCode === null || statusCode >= 400 || consoleErrors.length || pageErrors.length || requestErrors.length || !visible;
    let screenshot = null;
    if (failed) {
      screenshot = `capturas/${String(results.length + 1).padStart(2, '0')}-${slug(candidate.path)}.png`;
      try { await page.screenshot({ path: path.join(out, screenshot), fullPage: true, type: 'png' }); }
      catch { screenshot = null; }
    }
    results.push({ path: candidate.path, status: failed ? 'falla' : 'cumple', http_status: statusCode,
      final_url: finalUrl, console_errors: consoleErrors, page_errors: pageErrors,
      request_errors: requestErrors, visible_content: visible, screenshot,
      duration_ms: Date.now() - routeStart,
      reason: navigationError || (statusCode >= 400 ? `HTTP ${statusCode}` : !visible ? 'La página no mostró contenido visible.' : consoleErrors.length ? 'La consola registró errores.' : pageErrors.length ? 'La página lanzó una excepción JavaScript.' : requestErrors.length ? 'La página intentó una solicitud bloqueada o un recurso no cargó.' : null) });
    await page.close();
  }
  await context.close();
  await browser.close();
  const status = results.some(item => item.status === 'falla') ? 'falla'
    : results.some(item => item.status === 'sin_veredicto') ? 'sin_veredicto' : 'cumple';
  return { version: '1', status, startup: { ready: true, exit_code: null, port: plan.port,
    timeout_ms: plan.startup_timeout_ms, log: startup.join('').slice(-12000), reason: null },
    routes: results, duration_s: (Date.now() - startedAt) / 1000 };
}

try {
  const result = await main();
  fs.writeFileSync(path.join(out, 'e2e-result.json'), JSON.stringify(result, null, 2));
  process.exitCode = 0;
} catch (error) {
  fs.writeFileSync(path.join(out, 'e2e-result.json'), JSON.stringify({ version: '1', status: 'sin_veredicto',
    startup: { ready: false, exit_code: server?.exitCode ?? null, port: plan.port,
      timeout_ms: plan.startup_timeout_ms, log: startup.join('').slice(-12000), reason: clean(error.stack || error.message) },
    routes: [], duration_s: (Date.now() - startedAt) / 1000 }, null, 2));
  process.exitCode = 0;
} finally { stopServer(); }

// El servidor puede haber creado nietos (por ejemplo npm -> node). El JSON ya está
// sincronizado; terminar PID 1 hace que Docker limpie todo el espacio de procesos.
process.exit(0);
