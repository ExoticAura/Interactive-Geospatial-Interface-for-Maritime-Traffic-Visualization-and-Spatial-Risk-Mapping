// Minimal static file server for Railway deployment.
// Serves this folder as-is; no build step, no framework — just static HTML/JS.
const http = require('http');
const finalhandler = require('finalhandler');
const serveStatic = require('serve-static');

const serve = serveStatic(__dirname, { index: ['index.html'] });
const port = process.env.PORT || 3000;

const server = http.createServer((req, res) => {
  serve(req, res, finalhandler(req, res));
});

server.listen(port, () => {
  console.log('Maritime Risk Atlas Dashboard listening on port ' + port);
});
