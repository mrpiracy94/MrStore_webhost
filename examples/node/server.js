const http = require('node:http');
const port = Number(process.env.PORT || 3000);
const host = process.env.HOST || '0.0.0.0';
http.createServer((_req, res) => {
  res.writeHead(200, {'Content-Type': 'text/html; charset=utf-8'});
  res.end('<!doctype html><meta charset="utf-8"><title>Node.js no ZimaOS</title><body style="background:#0f172a;color:#a7f3d0;font:22px system-ui;padding:10%"><h1>🟢 Node.js online!</h1><p>O servidor npm start está a funcionar no MrStore_webhost.</p></body>');
}).listen(port, host, () => console.log(`Server listening at ${host}:${port}`));