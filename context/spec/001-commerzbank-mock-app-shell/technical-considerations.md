# Technical Specification: Mocked Commerzbank Mobile App Shell

- **Functional Specification:** [`functional-spec.md`](./functional-spec.md)
- **Status:** In Review
- **Author(s):** Viktor Kulyk (drafted with Claude; frontend input from the `react-frontend` agent)

---

## 1. High-Level Technical Approach

This feature **bootstraps the frontend project** (no application code exists yet) and builds the bank shell as a static, client-only React SPA. It doesn't call the backend: persona data is a static module, the "unlocked" state lives in memory, and quest-resume metadata lives in `localStorage`. The Railway API, `VITE_API_BASE_URL` and the anonymous session (`POST /session`) are introduced by the later Finance Quest specs.

**Stack, per `architecture.md` §1:**

- React 18 + TypeScript + Vite + Tailwind CSS
- deployed to Vercel as static files with an SPA catch-all rewrite

**Code split:** shell code and quest code live in separate folders, joined by two contracts:

1. a **quest-resume store**, which the shell reads and later game specs write
2. a **quest route prefix** (`/quest/*`), inside which the shell hides its chrome and the quest layout owns the ✕ button and leave dialog

The game itself is a one-screen stub ("What are you into?") until its own spec lands.

---

## 2. Proposed Solution & Implementation Plan (The "How")

### 2.1 Project layout

The frontend lives in `frontend/` at the repo root, which is the Vite root and the Vercel root directory. The Python API will sit beside it in its own directory.

| Path (under `frontend/`) | Responsibility |
| --- | --- |
| `index.html` | Viewport meta with `viewport-fit=cover`; English `lang` |
| `src/main.tsx`, `src/router.tsx` | Bootstrap; route table |
| `src/styles/index.css` | Tailwind layers, `@font-face`, base styles |
| `src/shell/AppFrame.tsx` | Root layout for all shell and quest routes: centred column (max 430 px), `ToastProvider`, `<Outlet/>` |
| `src/shell/ShellLayout.tsx` | Top bar + scroll area + tab bar for banking screens (not used on Welcome or quest routes) |
| `src/shell/TopBar.tsx` | Logo (Overview) or title; optional back arrow (StartDepot only) |
| `src/shell/TabBar.tsx` | 5 tabs, highlight derived from route (see 2.2) |
| `src/shell/Toast.tsx`, `src/shell/useToast.ts` | Single-instance "Not available in this demo." toast |
| `src/shell/Logo.tsx` | The only place the logo asset is referenced |
| `src/shell/ShellGuard.tsx` | Redirects to `/` while locked |
| `src/shell/screens/` | `Welcome.tsx`, `Overview.tsx`, `Investments.tsx`, `StartDepot.tsx`, `Placeholder.tsx` |
| `src/shell/components/` | `AccountCard.tsx`, `QuickActions.tsx`, `QuestCard.tsx` (variants `overview` / `depot`; Start vs Continue), `FaceIdAnimation.tsx` |
| `src/shell/data/persona.ts` | Fixed fictional persona, accounts and depot |
| `src/shell/lib/money.ts` | EUR formatting |
| `src/shell/lib/session.ts` | In-memory unlocked flag + context |
| `src/quest/QuestLayout.tsx` | Full-screen quest container: ✕ button, `LeaveDialog`, navigation blocker |
| `src/quest/LeaveDialog.tsx` | "Leave the quest? You can continue where you left off." with Leave / Stay |
| `src/quest/questStore.ts` | Quest-resume contract (see 2.4) |
| `src/quest/screens/WhatAreYouInto.tsx` | Stub first quest screen (title only) until the interest-picker spec |
| `src/assets/` | `commerzbank-logo.png` (provided by the team), font files if self-hosted beyond Fontsource |
| `vercel.json`, `playwright.config.ts`, `vitest` config, `.env.example` | Deployment and test config |

**Dependency rule:** `src/quest/` never imports from `src/shell/`, except the frame-level toast/context exports.

### 2.2 Routing

`react-router-dom` with a **data router** (`createBrowserRouter`), which `useBlocker` requires.

| Path | Screen | Highlighted tab | Guarded | Chrome |
| --- | --- | --- | --- | --- |
| `/` | Welcome | — | no | strip only |
| `/overview` | Overview | Overview | yes | strip + top bar + tab bar |
| `/investments` | Investments | Investments | yes | full |
| `/investments/startdepot` | StartDepot | Investments | yes | full + back arrow |
| `/payments`, `/service`, `/profile` | Placeholder (tab title + "This area isn't part of the demo.") | own tab | yes | full |
| `/quest`, `/quest/*` | Quest screens (stub: "What are you into?") | — | yes | strip + quest ✕ |
| `*` | redirect to `/` | — | — | — |

- **Reload always returns to Welcome:** `session.ts` holds a module-level `unlocked` flag that is never persisted, exposed through context.
  - `ShellGuard` wraps the guarded routes and redirects to `/` (replace) while locked. A reload resets the module, so any guarded URL lands on Welcome.
  - Face ID success sets the flag and navigates to `/overview` with `replace`.
  - The future `/stage` route will be an unguarded sibling, so it isn't affected.
- **Tab highlighting** comes from the first path segment: `/investments/*` maps to Investments.
- **Tab taps:**
  - Tapping an inactive tab pushes its root path.
  - Tapping the active tab replaces with its root path, so the Investments tab on StartDepot goes to `/investments`.
- **StartDepot back arrow:** `navigate(-1)`, which handles arrival from either Overview or Investments. On a direct entry with no history (`location.key === 'default'`), it falls back to `/overview`. Browser back on other shell screens is native history.
- **Entering the quest:** pushes `/quest` (or the resume path) with `state.origin` set to the shell path the player came from. Steps inside the quest use `replace`, so one browser back always exits the quest.
- **Leave dialog:**
  - `useBlocker` fires when navigating from `/quest*` to a non-quest path. It opens `LeaveDialog`: "Stay" resets the blocker and "Leave" proceeds.
  - ✕ triggers the same navigation, so ✕ and browser back share one code path.
  - If there is no history entry to go back to, ✕ navigates to `state.origin ?? '/overview'` with `replace`.

### 2.3 Data (static, fictional)

`src/shell/data/persona.ts` holds:

- `firstName: "Lena"`, with no age field
- `accounts`: one StartKonto, balance `1240.50`, number `"DE00 0000 0000 0000 0000 00"`
- `depot`: StartDepot, value `0`

The total balance is the sum of the account balances. There are no transactions.

`money.ts` uses `Intl.NumberFormat('en-IE', { style: 'currency', currency: 'EUR' })`, which renders `€1,240.50` and `€0.00`. A unit test checks the exact output, because ICU data can differ between environments.

### 2.4 Quest-resume contract (`questStore.ts`)

| Item | Definition |
| --- | --- |
| Storage | `localStorage["fq.quest.v1"]` |
| Shape | `{ v: 1, status: "in_progress" \| "finished", lastPath: string, savedAt: number, state: unknown }`. `state` is opaque and owned by later quest specs |
| Shell reads | `getQuestMeta() → { inProgress: boolean, resumePath: string }`, reactive via `useSyncExternalStore` |
| Quest writes | `startQuest()` (writes `in_progress`, `lastPath: "/quest"`), `saveProgress(path, state)`, `finishQuest()`, `clearQuest()` |
| Robustness | Every access is wrapped in try/catch, with an in-memory fallback if storage throws (private mode). A parse error, wrong `v` or missing field is treated as "no quest" and the key is removed. A breaking change bumps the key (`v2`) |

**Behaviour:**

- `QuestCard` shows "Quest in progress" + "Continue" while `inProgress`, and navigates to `resumePath`. Otherwise it shows "Start" / "Start your first quest" and calls `startQuest()` before navigating.
- `startQuest()` writes immediately, so "Continue" also appears if the player leaves at once.
- Resume survives reload. The unlocked flag does not, so the player unlocks again and then sees "Continue".

### 2.5 Visual system

**Tailwind 3.4 theme tokens** (in `tailwind.config.ts`; values from the brand research in `research-notes.md`):

| Token | Value | Use |
| --- | --- | --- |
| `brand.yellow` | `#FFD700` | Finance Quest cards, accents |
| `petrol` | `#002E3C` | Text, primary buttons, active tab |
| `petrol-muted` | `#506C74` | Secondary text, inactive tabs |
| `warm` | `#F1EFED` | Screen background |
| `line` | `#CED8DA` | Dividers |
| white | `#FFFFFF` | Cards |
| `demo` | `#6B21A8` with white text (contrast ≈ 9.4:1) | Demo strip only; used nowhere else |
| `rounded-card` | 16 px | Cards |
| `rounded-pill` | 9999 px | Buttons |

**Layout:**

- `AppFrame` uses `min-h-dvh`, `max-w-[430px]` and `mx-auto`, so on a laptop it shows as a centred column. The page background outside the column is `warm`.
- `DemoStrip` is sticky at the top, 24 px plus `env(safe-area-inset-top)`, with the highest z-index.
- The top bar is sticky below the strip.
- The tab bar is fixed at the bottom, centred, at most 430 px wide, with `env(safe-area-inset-bottom)` padding. The scroll area gets matching bottom padding so no content hides behind it.
- The toast and dialog sit above the content but below the strip, offset by the strip's height, so the strip is always visible.

**Typeface:** Montserrat 400/500/700 via `@fontsource/montserrat`, self-hosted with no Google CDN, as the free geometric stand-in for Gotham. The font stack is `['Gotham', 'Montserrat', sans-serif]`. To swap in Gotham later, add licensed `.woff2` files and an `@font-face` rule, with no component changes.

**Icons:** `lucide-react` for the tab bar, quick actions, back arrow and ✕. The real app's icon set is unverified, so these don't claim to match it.

**Logo:** `Logo.tsx` renders `src/assets/commerzbank-logo.png` with alt text "Commerzbank".

- **The file:** the team provided it. It is 1280 × 230 px, the 2009 mark: a black "COMMERZBANK" wordmark with the yellow-orange ribbon on the right, on a transparent or white background.
- **Sizing:** it is scaled down by height, about 20–24 px in the top bar and about 32–40 px on the Welcome screen. It is suitable for light backgrounds only, which is fine because the shell is light mode only.
- **Swapping it:** `Logo.tsx` is the only place the file is referenced, so a sharper SVG or the 2021 refined mark can replace it later without other changes.

### 2.6 Interaction components

- **Face ID (`FaceIdAnimation.tsx`):**
  - Inline SVG with CSS keyframes, no animation library.
  - About 1.1 s scan sweep, then about 0.4 s check-mark draw-in; a 1.5 s timer then navigates.
  - The button is disabled during the animation.
  - Under `prefers-reduced-motion`, it shows static frames with the same 1.5 s timing.
  - It must never call `getUserMedia`, `navigator.credentials` or any WebAuthn or camera API (enforced by test, see §4).
- **Toast:**
  - One provider with state `{ id } | null`.
  - `show()` clears any pending timer, bumps `id` (re-keying the element so it re-animates), and sets a 3000 ms timer. A tap dismisses it.
  - It uses a persistent `role="status"` / `aria-live="polite"` region, so two toasts never stack.
- **Tappable inventory:** every button, card, list entry, quick action and tab either navigates or calls `toast.show()`. The unavailable ones are:
  - the StartKonto card
  - Transfer, Cards and Postbox
  - "Set up savings plan"

### 2.7 Deployment

- **`frontend/vercel.json`:** a single rewrite of all paths to `/index.html` (static assets are served first).
- **Vercel project settings:** Vite preset, root directory `frontend`, build `npm run build` (`tsc -b && vite build`), output `dist`.
- **Environment variables:** none for this feature. Add `.env.example` with a commented `VITE_API_BASE_URL` for the later specs.

---

## 3. Impact and Risk Analysis

**System dependencies:**

- No backend dependency.
- Later specs depend on this one for:
  - the quest route prefix and `QuestLayout` (✕, leave dialog, blocker)
  - the `questStore` contract
  - `AppFrame` / `DemoStrip` / toast
  - the theme tokens
- The future `/stage` page (separate spec) will embed or link this app and must sit outside `ShellGuard`.

**Potential risks and mitigations:**

| Risk | Mitigation |
| --- | --- |
| Reload-to-Welcome guard breaks deep links or the future `/stage` route | Guard applies only to shell and quest routes; `/` and `/stage` are unguarded siblings |
| Navigation blocker loops or traps the user (no history entry, repeated back) | `replace` for steps inside the quest; ✕ falls back to `state.origin ?? "/overview"` with `replace`; e2e tests for both paths |
| iOS Safari edge swipe-back can't be fully intercepted | Dialog is best-effort on swipe; one history entry per quest keeps back predictable; manual check on a real iPhone before the stage demo |
| Logo is a raster PNG of the 2009 mark; Gotham isn't licensed | Logo isolated in `Logo.tsx` (swap for an SVG or the 2021 mark later); Montserrat in a single font stack |
| Real tab bar, icons and Overview layout unverified | Generic icons, no claim of exactness; replace from teammate screenshots (TODO in research notes) |
| Quest-resume data churn as game specs evolve | Versioned key, opaque `state`, defensive parsing that discards bad data |
| `localStorage` unavailable (private mode, blocked storage) | In-memory fallback: resume works within the tab, just not across reloads |
| iOS dynamic toolbars shifting fixed elements | `dvh` units, safe-area insets, no `vh` |
| Currency string differs across ICU versions | Exact-string unit test; e2e runs in the same browsers as the demo |

---

## Decisions confirmed on 2026-11-20

- Logo: the team-provided PNG, moved to `frontend/src/assets/commerzbank-logo.png`.
- Typeface: Montserrat, as the stand-in for Gotham.
- Tailwind: 3.4.
- Demo strip colour: deep purple `#6B21A8` with white text.

---

## Change on 2026-11-20

The demo strip was removed at the user's request, which changes four things:

- **Components:** `DemoStrip` and its token use are gone. The `demo` colour token is no longer used.
- **Layout:** the top bar sticks at `top-0` with `env(safe-area-inset-top)` padding. The welcome screen and quest layout carry the top safe-area padding themselves. The leave dialog no longer offsets for a strip.
- **Earlier decisions:** where earlier sections mention the demo strip, the strip colour or z-index ordering relative to the strip, those statements no longer apply.
- **Tests:** the requirement-2.2 tests now assert that no strip is shown.

---

## 4. Testing Strategy

**Commands** (all run from `frontend/`):

- `npm run test`: Vitest
- `npm run e2e`: Playwright, which starts `vite preview` via `webServer`
- `npm run typecheck`
- `npm run lint`

**Unit / component tests** (Vitest + React Testing Library, jsdom):

- `money`: exact `€1,240.50` / `€0.00`
- `Toast`: 3 s auto-dismiss, tap-dismiss, replace-and-restart with fake timers, a single live region
- `questStore`: fresh, in-progress, finished, corrupt JSON, wrong version, storage throwing
- `TabBar`: highlight per route, including StartDepot → Investments
- `TopBar`: back arrow only on StartDepot
- `QuestCard`: Start vs Continue
- `ShellGuard`: redirect while locked

**End-to-end tests** (Playwright, Chromium + WebKit). Viewport projects are 360×740, 430×932 and 1280×800; together the tests cover every acceptance criterion in the functional spec:

- **Welcome:** content and no input fields. Face ID shows a check mark after about 1.5 s, then the Overview.
- **No camera or credential calls:** `getUserMedia` and `navigator.credentials` are stubbed and asserted never called, with no permissions granted. CI also greps `src/` for those APIs.
- **Reload on any screen:** returns to Welcome.
- **Overview:** element order, texts and values. The Finance Quest card is within one screen height at 360 and 430.
- **Layout:** no horizontal scroll (`scrollWidth <= innerWidth`). At 1280 the column is at most 430 px wide and centred.
- **Computed styles:** the quest card is `#FFD700`, body text and primary buttons are `#002E3C`, the background is `#F1EFED`, cards have a 16 px radius, and buttons are pill-shaped.
- **Tabs:** order, highlighting and placeholder text. StartDepot is reachable from both places; the back arrow returns to the right origin; the Investments tab from StartDepot goes to Investments.
- **Toast:** appears for each unavailable element; only one at a time; gone after 3 s; the strip stays visible above it.
- **Tap sweep:** every tappable element either navigates or shows the toast.
- **Demo strip:** visible on every shell screen, on the quest stub, and above the toast and dialog; it never covers content after scrolling to the bottom.
- **Quest:**
  - ✕ and browser back both open the dialog; "Stay" stays; "Leave" returns to the origin with the chrome back.
  - "Quest in progress" and "Continue" show after leaving, and after a reload and unlocking again.
  - "Continue" opens the last quest path.

**Manual checks before the stage:**

- a real iPhone (Safari): swipe-back, safe areas, Face ID animation smoothness
- a real Android phone (Chrome)

Screenshots go to `docs/screenshots/`, captured with the Playwright MCP.
