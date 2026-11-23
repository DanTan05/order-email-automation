# Order Email Automation

Reads customer order emails, pulls out the order lines with Google Gemini, checks them against business rules in pandas, and writes them to a Google Sheet: a **Clean** tab for lines that are ready to process, and a **Review** tab for lines a person needs to check.

Built for a perfume and cosmetics trading company, where orders arrive by email in many formats and are currently typed into a spreadsheet by hand.

## The problem

Every customer writes orders differently:

- a neat list with prices: `Oud Royale 100ml EDP x 24 @ AED 185 each`
- a missing price: `please confirm your current price`
- quantities in words: `two dozen`, `fifty pieces`
- vague prices: `same prices as last month`
- a table in a different currency (USD)
- an email that isn't an order at all (a complaint)

Retyping these by hand is slow, and it's easy to miss a line or invoice the wrong price.

## How it works

```
emails/*.txt
   │
   ▼
extract_one.py   Gemini reads the email → JSON in a fixed schema (pydantic)
   │
   ▼
output/json/     cache: each email is sent to Gemini only once
   │
   ▼
run_pipeline.py  one row per order line
   │
   ▼
validate.py      fix types → match catalog → line total → flag issues
   │
   ▼
sheets.py        Google Sheet → "Clean" tab + "Review" tab
```

The LLM is used only to read the text. Anything that has to be exact (numbers, totals, catalog matching, the rules) is plain Python, which is tested.

- **Structured output:** Gemini must answer in the `Order` schema, at temperature 0.
- **No guessing:** the prompt tells Gemini to return `null` with a note when something isn't in the email (e.g. "same prices as last month" → price `null`).
- **Rules** in `validate.py`: `missing_price`, `bad_quantity`, `unknown_product`, `missing_currency`, `not_an_order`. A row with any flag goes to Review.
- **Catalog matching:** `difflib` fuzzy match (cutoff 0.8) maps spelling variations to the official product name.

## Results on the 5 sample emails

| Email | Case | Result |
|---|---|---|
| 01 | clean list, AED | 3 lines → Clean |
| 02 | one price missing | 1 Clean, 1 Review (`missing_price`) |
| 03 | "two dozen", "fifty pieces", "same prices as last month" | quantities 24 and 50 read correctly; both → Review (`missing_price`) |
| 04 | table in USD, one product not in catalog | 2 Clean, 1 Review (`unknown_product`) |
| 05 | complaint, not an order | 1 Review (`not_an_order`) |
| **Total** | | **11 lines: 6 Clean, 5 Review**, all as expected |

7 unit tests for the rules pass (`pytest`).

## Tech

Python 3.12 · `google-genai` (Gemini) · `pydantic` · `pandas` · `gspread` (Google Sheets, service account) · `python-dotenv` · `pytest`

## Project structure

```
src/
  extract_one.py    Gemini call + Order schema + prompt
  validate.py       business rules
  sheets.py         writes a DataFrame to a Sheet tab
  run_pipeline.py   runs everything end to end
tests/
  test_validate.py  unit tests for the rules
data/catalog.csv    product list (9 products)
emails/             5 sample emails (made up for testing)
.env.example        which keys are needed
```

## How to run

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

pytest -v                                        # rules: 7 passed
python src/extract_one.py emails/email_01.txt    # Gemini on one email
python src/run_pipeline.py                       # full pipeline
```

Setup needed once:
1. Copy `.env.example` to `.env` and add a Gemini API key and the Google Sheet ID.
2. Create a Google Cloud service account, save its key as `credentials/service_account.json`, and share the Sheet with the service account's email as Editor.

`.env`, `credentials/` and `output/` are git-ignored.

## Known limitations / next steps

- No timeout or automatic retry on the Gemini call yet (a 503 needs a re-run).
- USD rows land in Clean next to AED rows, so summing totals mixes currencies. Next: flag or convert foreign currency.
- Each run clears and rewrites the tabs, so edits made in Review are lost.
- No check of email prices against the catalog list price.
- Emails are local text files; the next step is reading from a real inbox (Gmail/Outlook API).

More detail on every file and design decision: [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md).
