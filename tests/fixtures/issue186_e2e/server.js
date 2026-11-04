import express from 'express';

const app = express();
app.get('/', (_req, res) => res.send('<main><h1>QAgent E2E correcto</h1></main>'));
app.get('/otro', (_req, res) => res.send('<main>Otra ruta visible</main>'));
app.get('/error-http', (_req, res) => res.status(500).send('<main>Error real 500</main>'));
app.get('/error-js', (_req, res) => res.send('<main>Error JS</main><script>throw new Error("fallo fixture")</script>'));
app.get('/vacia', (_req, res) => res.send('<!doctype html><html><body></body></html>'));
app.get('/red-externa', (_req, res) => res.send('<main>Red</main><script>fetch("https://example.com/qagent-control")</script>'));
app.listen(Number(process.env.PORT || 4173), '127.0.0.1', () => console.log('fixture ready'));
