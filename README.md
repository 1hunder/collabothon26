# Finance Quest

Finance Quest is a mobile-first investing game set inside a simulated Commerzbank banking app. Each campaign turns a historical market case into a mystery. Explore locations, question characters and review evidence before making an investment decision with simulated funds. The reveal shows which company you investigated and what happened in the market.

## Run the demo with Docker

From the repository root, start the full stack with Docker Compose. The first file defines PostgreSQL and the API. The second adds the web app and enables scripted narration by default, so you can play without API keys or a local `.env` file.

```sh
docker compose -f docker-compose.yml -f compose.yaml --profile api up --build -d
```

On startup, the API applies database migrations and approves the bundled reference case. Check that the app can reach the API and that at least one case is ready to play.

```sh
curl -fsS http://localhost:4173/api/healthz
```

Look for `"db":true` and a `playable_count` of at least 1. If the API has just started, give it a moment to finish setup. For startup errors, run `docker compose -f docker-compose.yml -f compose.yaml --profile api logs api`.

### Play your first quest

1. Open [the local app](http://localhost:4173) and tap **Unlock with Face ID** to enter Lena’s demo account. The unlock is simulated.
2. On **Overview**, find **Finance Quest** and tap **Start**. Choose a character class and select **Begin**.
3. Read the Campaign Master’s briefing. Follow a suggested action, write your own or use the map to travel. Tap the CommerzBuddy mascot to ask about a clue or financial term.
4. Commit to an investment decision and follow the outcome through the company reveal. If you leave early, **Continue** on Overview resumes your quest.

To stop the stack and keep its database and generated quest files for your next session, run:

```sh
docker compose -f docker-compose.yml -f compose.yaml --profile api down
```

## Development

The [React frontend](frontend/) uses TypeScript, Vite and Tailwind. The [Python backend](backend/) serves the FastAPI API, runs the campaign engine and stores progress in PostgreSQL. With Docker running, you can explore the endpoints in the [local API docs](http://localhost:8000/docs).

**Frontend.** For UI work with fixture data, use Node.js 24 and run the following from `frontend/`. Open the local URL printed by Vite. Run `npm test` in the same directory for the Vitest suite.

```sh
npm ci
VITE_API_MODE=fixture npm run dev
```

To develop against the running Docker API, start Vite with `VITE_API_BASE_URL=http://localhost:8000 npm run dev` instead.

**Backend.** With the Docker database running on its default port (5432), run the following from `backend/` using Python 3.12 and uv. The test suite creates and removes a temporary database on that PostgreSQL instance.

```sh
uv sync --frozen
FAKE_LLM=1 uv run pytest -q
```

For optional model and storage settings, see the [environment example](.env.example). For Railway and Vercel setup, see the [deployment guide](docs/deploy.md).
