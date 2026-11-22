# Dice & Dividends

Dice & Dividends is a fantasy role-playing game for your phone, built for the Commerzbank "Finance Quest" challenge at Collabothon 2026. Create a hero, pick a quest, explore a village, question its characters and roll dice while an AI Campaign Master runs the story. Underneath, every quest is a real market case with the company disguised and the ending hidden, so your hero's big decision is a real investment judgment. The reveal shows which company you were dealing with and what really happened. It runs inside a simulated Commerzbank banking app with simulated funds.

## Project card

**Project name:** Dice & Dividends

**One-line summary:** A fantasy role-playing game in the Commerzbank app: young players create a hero, roll dice and spend gold in quests built on real market history, and learn to invest along the way.

**Technology stack:** Frontend: TypeScript, React 18, Vite, Tailwind CSS, TanStack Query, React Router, TradingView Lightweight Charts. Backend: Python 3.12, FastAPI, Pydantic, SQLModel, Alembic, PostgreSQL, Server-Sent Events. AI: Anthropic Claude (Opus 5.5) orchestrated with LangGraph and langchain-anthropic; Google Gemini for scene art and voice narration (TTS). Data: yfinance price history, hand-researched case packs. Infrastructure: Docker, Railway (API, PostgreSQL, storage bucket), Vercel, GitHub Actions. Testing: pytest, ruff, mypy, Vitest, Testing Library, Playwright.

**Source code:** https://github.com/1hunder/collabothon26

### The problem

Young people aged can open a free Commerzbank StartDepot, yet most keep their money in a savings account. Information is not what holds them back; confidence is. Every chart looks scary, a normal dip is hard to tell from real trouble, and "Investing 101" content feels like homework, far from a real decision. Practising on history doesn't help either when you already know how the story ended.

### Your solution

Dice & Dividends is first of all a role-playing game, in the spirit of a tabletop RPG night. You create a hero, pick a quest from the guild's Quest Board and play through a story run by an AI Campaign Master (the game master): travel a fantasy village, talk to its characters, roll dice for skill checks, spend gold, lose health and earn XP and items. What makes it different is the story underneath. Every quest is a real market case (a company in a crisis or a boom) disguised as a fantasy guild with the ending hidden. When the hero decides whether to back the guild, it is a real investment judgment under uncertainty, with a forecast and a confidence level. Then time skips forward, the guild is revealed as the real company, and the debrief separates good judgment from good luck. The game never gives investment advice, and an engine, not the AI, decides every number.

### The working prototype

A complete RPG, deployed and playable on a phone, launched from a mocked Commerzbank app (the Face ID unlock is simulated).
- Heroes: three classes (Guardian, Analyst, Investigator) with their own health, dice rerolls and perks; XP, items and a learning history carry over between quests.
- Quests: a Quest Board with four curated quests from real history (Enron 2001, GameStop 2021, Netflix 2022, Nvidia 2023), plus personal quests the game writes from the player's (mock) card spending.
- Play: free-text role-play with a streamed, voiced Campaign Master; a village map with the Tavern, the Market Square and the Library; characters to question; glowing objects in painted scenes; dice rolls for risky actions; gold and health at stake.
- Companions: CommerzBuddy, a mascot who explains terms and pops up with short learning moments, and the Veteran in the Tavern, who retells finished quests with the real company.
- Finale: the decision, a time skip, the outcome in gold, the reveal of the real company with real dates and headlines, a debrief and XP.
- The whole game also runs with scripted narration and no API keys, for a safe stage demo.

### Behind the build

A React + TypeScript app (Vercel) talks to a FastAPI service (Docker on Railway, PostgreSQL). A deterministic Python engine owns every price, date, dice roll, portfolio value and score, and a story clock withholds all data after "story today" on the server, not just in the UI. Claude runs as nodes in fixed LangGraph graphs: narration, CommerzBuddy, XP judging, the debrief, and a per-company agent that finds a price shock in yfinance data, researches it with web search and drafts a disguised quest. Every model reply passes deterministic guards for unknown numbers, real-name leaks, spoilers and advice before it streams to the player over SSE. Gemini paints scene art from scrubbed prompts and voices the narration. We built the app, engine, agents, case packs and art pipeline during the hackathon, on top of open-source libraries (FastAPI, SQLModel, LangGraph, Lightweight Charts, Tailwind) and public price data.

### Challenges and discoveries

- Hiding a famous company is hard: one detail (a product, a CEO, an exact figure) gives it away. We added a re-identification gate where Claude plays the adversary and tries to guess the company, plus a deterministic leak scan.
- Language models like to invent numbers. Letting the engine own every figure and checking each reply against an allowlist fixed it.
- We tried preset answer buttons and removed them: writing your own reasoning teaches more than picking an option.
- Live voice and image generation are slow, so both run with limits, caching and fallbacks.

### Results and next steps

We achieved a complete RPG quest that is playable end to end on a phone, from hero creation to the real-company reveal, with four curated quests and live generation of new ones. We validated it with more than 900 automated tests (engine math, the hidden-future gate, guards, anonymisation, UI), Playwright end-to-end runs including a live Enron playthrough, and CI on every pull request. The moment we are proudest of: the reveal, when the guild your hero has been trading turns out to be Enron.
Limitations: unofficial Yahoo Finance prices and hand-researched cases; English only; the StartDepot savings plan is a mock and not yet linked to the quest.
Next: more quests and classes, a campaign that spans several quests, linking the debrief to a first savings plan, licensed price and news data, and play-testing with young Commerzbank customers.

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
