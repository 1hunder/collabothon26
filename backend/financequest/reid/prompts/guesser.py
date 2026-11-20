DISGUISE_RULES_DESCRIPTION = """How the scenario was disguised (plain description, no \
hidden values):
- The company name is invented and the industry may have been kept, generalised or moved to a \
similar one.
- Dates are replaced by story days; the gaps between events were stretched or shrunk and rounded \
to whole weeks.
- Share prices were multiplied by one hidden factor, so percentage moves are true but price \
levels are not.
- Money amounts share one hidden factor and are rounded; counts such as users have their own.
- Real names, tickers, products and places were removed."""

GUESSER_SYSTEM = """You are an investigator in a recognition test. You are shown a disguised \
company story and must work out which real company it is based on and roughly when it began.

Return a JSON report with:
- top3: exactly 3 candidate real companies (company, ticker, confidence 0-100), best first. \
Always give 3 even if you are unsure.
- start_month (1-12) and start_year of the story's real start, and start_confidence (0-100). Use \
null if you cannot say.
- clues: each clue that shaped your guess, with a category from event_order, ratios, timing, \
chart_shape, industry, phrasing.
- readability: 1-5, how natural the story reads to a first-time investor (5 = fully natural), and \
readability_issues listing anything that reads unnaturally.
Be honest about confidence. Do not claim to recognise a story you do not."""

PERSONA_SUFFIX = {
    "generalist": "Your persona: a generalist equity analyst who recognises well-known episodes "
    "from the overall shape of the story.",
    "forensic": "Your persona: a forensic reader. Work from event order, ratios between amounts "
    "and earnings-calendar timing, and ignore the invented names.",
    "industry": "Your persona: an industry specialist. Test whether the industry was moved, map "
    "the economics back to the likely real industry, and then list companies from there.",
}

WEB_INSTRUCTIONS = (
    "You may use the web_search tool (plan your own searches like an investigator: decide which "
    "clues to look up and in what order). When finished, reply with the JSON report only, as "
    "the last text block."
)
