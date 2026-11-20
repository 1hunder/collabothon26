# Finance Quest: anonymization / re-identification test report

Date: 2026-11-20. Scope: proof of concept. Tests whether the anonymization layer in the
Finance Quest concept can turn real market history into a scenario that a player or an LLM
sees "for the first time".

## Setup

- **Inputs:** the 6 cases from `gamified_investing_articles_ru.md` (Netflix, Boeing, Nvidia, Meta,
  Spotify, Intel, 2023–2024). Each case has 2–4 dated news beats and prices
  (`data/source_cases.json`). The prices are approximate values from memory, not pulled from Yahoo.
  They are realistic in shape, which is all this test needs.
- **Pipelines under test:**
  - **POC**: rule-based only (`src/poc_anonymizer.py`). Fictional name, people removed, dates turned
    into story days, prices rescaled. Facts are otherwise kept verbatim.
  - **PROD v1**: POC rules plus an LLM semantic scrub (`src/prod_anonymizer_spec.md`). Product, place
    and org names removed, iconic events paraphrased, amounts rescaled, no years, months or quarters.
  - **PROD v2**: one turn of the re-identification loop proposed in the concept. The generator
    got the attackers' round-1 findings (`src/round1_attacker_feedback.md`) and moved each story to
    an analogous industry, dropped one fingerprint detail, and scaled each kind of metric by its own
    factor. Code then jittered the timeline into weeks and changed each price move by ±25%, keeping
    its direction (`src/prod_v2_postprocess.py`).
- **Attackers:** 18 fresh sub-agents (Claude), one per blinded scenario (`attacks/T01–T18`). Each saw
  only its scenario and was told how the disguise works (worst case: the method is known). Each
  guessed the company and start month twice: first from memory alone, then with up to 6 web
  searches. It also rated how natural the story reads to a beginner (1–5).
- **Deterministic checks:** `src/check_integrity.py` checks that price moves and day gaps match the
  real data and scans for banned tokens (real names, products, years, months, quarters, distinctive
  figures).

## Results

| Pipeline | Re-identified, memory only (top-1) | Re-identified, with web search (top-1) | Mean attacker confidence, memory only | Disguise strength* | Data integrity | Coherence | **Overall quality** |
|---|---|---|---|---|---|---|---|
| POC | 6/6 | 6/6 | 96.8% | 2 / 100 | 44 | 67 | **27 / 100** |
| PROD v1 | 6/6 | 6/6 | 93.3% | 5 / 100 | 98 | 75 | **45 / 100** |
| PROD v2 (one re-id loop turn) | 6/6 | 6/6 | 87.2% (lowest 75%) | 10 / 100 | 100 | 67 | **43 / 100** |

\*Disguise strength = 100 − the attacker's mean confidence in the correct answer, averaged over the
memory-only and web-search guesses. The re-identification privacy score (top-1 = full breach,
top-3 = half, start month within 3 months = +0.25) is **0 for all three pipelines**.

Overall = 0.5 × privacy + 0.3 × integrity + 0.2 × coherence. Privacy carries the most weight
because it is the product's core promise ("Claude knows how 2020 ended. Our players don't").

The start month was correct in 18 of 18 attacks. Most attackers did not need web search at all:
memory alone was enough.

## What gave the cases away

1. **The sequence of events is the fingerprint, not the names.** "Safety grounding → machinists'
   strike → 10% cuts plus delay of the next model → strike ends" was recognised as Boeing even after
   it was moved to a surgical-equipment maker. Moving to another industry also made the story less
   believable: the attacker scored it 3/5 and noted that medtech does not ground hundreds of units
   at once.
2. **The timing pattern.** Real day gaps match the quarterly earnings calendar. Even after jitter,
   attackers mapped the beats onto earnings dates.
3. **Ratios survive scaling.** Within one metric family the ratios stay the same, e.g. subscriber
   net adds of 1 : 1.5 : 2.2, or a guidance-vs-consensus gap of 1.54×. One known figure is enough
   to recover the scale factor.
4. **Price shape.** Even with ±25% noise, "roughly tripled in a year" or "fell about 45%" is enough
   to confirm a guess from memory.
5. **POC only:** verbatim wire headlines (one search finds them), product names, and literal years.

## Verdict

- Your colleague is right for this case set. These six stories are among the most heavily covered
  stock stories of 2023–24, and current models know them very well. No amount of text rewriting
  hid them: the best version still left the attacker 75–95% sure.
- Production beats the POC on data integrity and spec compliance (no leaked tokens, prices exact)
  and slightly on disguise strength. The re-id loop does push confidence down (96.8 → 87.2), but
  one turn is far from enough.
- **The re-identification test works as a gate.** It caught all 18 breaches automatically, with
  clear reasons. This is the most reusable part of the pipeline: keep it as a mandatory step before
  any one-shot is shown.

## Recommendations for the hackathon build

1. **Change the case selection, not just the text.** Generate one-shots from less famous companies:
   small or mid caps, non-US listings, or periods before 2015. The famous six can serve as the
   "reveal" showcase rather than the hidden scenario.
2. **Blend sources:** take the price path of one obscure stock and the news beats from a
   different, similar company. Or keep the real price shape and write generic beats that explain
   it. That stays honest to "real prices", and no single real story remains to recognise.
3. **Gate on the re-id test:** regenerate or swap the case while attacker confidence exceeds a
   threshold, e.g. 30% top-1 from memory. Cap the loop at 2–3 tries, then pick a different case.
4. **For the demo,** do not claim "neither the player nor Claude can recognise the scenario" for
   famous companies. Rephrase it as "every one-shot passes an automatic re-identification test
   before you see it". This test shows that the claim holds only with an enforced gate.

## Caveats

- n = 6 cases per pipeline, and the attacker is the same model family as the generator. The
  results are a signal, not a benchmark.
- Prices are approximate values from memory, not market data.
- Real players are far weaker attackers than an LLM with web search. Even so, the memory-only
  results are what the "Claude can't recognise it" claim depends on.
