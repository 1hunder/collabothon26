# Finance Quest frontend

Mocked Commerzbank app shell (spec 001): a demo-only, mobile-first React + Vite + Tailwind app that imitates the Commerzbank banking app (welcome screen, Overview, Investments, StartDepot, StartKonto) and hosts the Finance Quest entry points. There is no backend dependency and no real banking data.

## Local development

Run from `frontend/`:

| Command | Purpose |
| --- | --- |
| `npm install` | Install dependencies |
| `npm run dev` | Vite dev server |
| `npm test` | Unit tests (Vitest) |
| `npm run e2e` | End-to-end tests (Playwright) |
| `npm run typecheck` | `tsc -b --noEmit` |
| `npm run lint` | ESLint |
| `npm run build` | `tsc -b && vite build`, output in `dist/` |
| `npm run preview` | Serve the production build on port 4173 |

## Deploying to Vercel

Create a Vercel project from this repository with these settings:

| Setting | Value |
| --- | --- |
| Root Directory | `frontend` |
| Framework Preset | Vite |
| Build Command | `npm run build` |
| Output Directory | `dist` |
| Environment Variables | none for this feature |

`VITE_API_BASE_URL` is not used yet; it arrives with the later API specs and is set per environment in Vercel (see `.env.example`). Never put secrets into the frontend build.

### Deep links and reload behaviour

`vercel.json` rewrites every path to `/index.html` (static files in `dist/` are served first), so deep links such as `/investments/startdepot` load the SPA instead of returning a 404. This rewrite was checked locally by serving the production build with a single-page-mode static server (`npx serve -s dist`), which applies the same rule: `/`, `/investments/startdepot`, `/quest` and hashed assets under `/assets/` all returned 200, and the deep link returned the `index.html` shell.

By design, a reload (or opening any deep link directly) always returns to the welcome screen; the shell is guarded so the demo always starts from the welcome screen.
