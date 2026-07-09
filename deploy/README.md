# Maritime Risk Atlas Dashboard

Static, self-contained interactive prototype — no build step required.

## Contents
- `index.html` — main dashboard (map, sidebar, KPIs, timeline, risk drawer, vessel popup, 3D side-view, settings modal, mobile variant)
- `design-system.html` — design system / style guide page
- `support.js` — runtime the pages depend on (do not remove or rename)
- `server.js` + `package.json` — tiny static file server for Railway

## Deploy on Railway
1. Push this folder to a GitHub repo (this folder should be the repo root, or set Railway's root directory to it).
2. In Railway: **New Project → Deploy from GitHub repo**, pick this repo.
3. Railway detects Node via `package.json` and runs `npm start` automatically (`node server.js`). No other config needed — no database, no env vars required.
4. Once deployed, Railway gives you a public URL. `/` loads the dashboard, `/design-system.html` loads the style guide.

## Notes
- The app loads Leaflet, Leaflet.heat, Three.js, and Google Fonts from public CDNs at runtime — the deploy target needs outbound internet access (Railway's default is fine).
- All data (vessels, risk zones) is mock/sample data generated client-side; there is no backend or database.
- Pure static site — you could alternatively deploy it on Vercel/Netlify/GitHub Pages by pointing to `index.html` directly and skipping `server.js` entirely. `server.js` exists only because Railway expects a running process.
