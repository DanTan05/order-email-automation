# Order Email Automation: Project Overview

Turns customer order emails into a checked, structured order list in Google Sheets. An LLM (Google Gemini) reads each email, pandas checks every order line against business rules, and the results go into two tabs: **Clean** (ready to process) and **Review** (needs a human).

---

## 1. The problem

A perfume and cosmetics trading company gets purchase orders by email from many customers. Every customer writes differently:

- a neat bullet list with prices (`Oud Royale 100ml EDP x 24 @ AED 185 each`)
- a sentence with a price missing (`please confirm your current price`)
- quantities written in words (`two dozen`, `fifty pieces`)
- vague references (`same prices as last month`)
- a table in a different currency (USD)
- emails that aren't orders at all (a complaint about a damaged shipment)

Today someone reads each email and types the lines into a spreadsheet by hand. This is:

- **slow:** every order line is retyped
- **error-prone:** wrong quantities, wrong product names, missed lines
- **inconsistent:** the same product gets spelled several ways
- **risky:** a missing price can slip through and the order is invoiced wrong

## 2. Why this solution

| Need | How the project meets it |
|---|---|
| Read free-form text in any format | An **LLM** (Gemini) understands language that fixed rules (regex) can't, e.g. "two dozen" = 24 |
| Never invent data | The prompt says "never guess, use null". Temperature is 0, and output is forced into a fixed **schema** (pydantic) |
| Catch problems before they cost money | **Rule-based validation** in pandas flags missing prices, bad quantities, unknown products and non-orders |
| Keep a human in control | Problem rows go to a separate **Review** tab rather than being dropped or auto-fixed |
| Use a tool the business already has | Output goes to **Google Sheets**, so nobody needs to learn new software |
| Change rules safely | The rules are covered by **pytest** tests |

**Key design idea:** the LLM is used only for what it's good at (understanding text). Everything that must be exact (numbers, totals, catalog matching, business rules) is done by normal, testable Python code.

## 3. How it works (data flow)

```
emails/*.txt
   │
   ▼
[extract_one.py]  Gemini reads the email → structured Order (JSON)
   │                 decides is_order, products, quantities, prices, currency
   ▼
output/json/*.json   cache: each email is sent to Gemini only once
   │
   ▼
[run_pipeline.py]  flatten: 1 email → 1 row per product line
   │
   ▼
[validate.py]      clean types → match catalog → line_total → flag issues
   │
   ├──► output/orders.csv          (all rows, local copy)
   │
   ▼
[sheets.py]        Google Sheet "Orders"
                     ├── Clean tab   (issues == "")
                     └── Review tab  (anything flagged)
```

## 4. Tech stack

| Tool | Used for |
|---|---|
| Python 3.12 + venv | language, isolated environment |
| `google-genai` | calling Gemini (`gemini-3.6-flash`) with structured output |
| `pydantic` | defining the Order schema and checking Gemini's JSON against it |
| `pandas` | table operations, type cleaning, rule masks |
| `difflib` (standard library) | fuzzy matching of product names to the catalog |
| `gspread` + Google service account | writing to Google Sheets |
| `python-dotenv` | loading secrets from `.env` |
| `pytest` | unit tests for the validation rules |

## 5. Project structure

```
order-automation/
├── .env                     ← secrets: GEMINI_API_KEY, SHEET_ID        (git-ignored)
├── .env.example             ← template showing which keys are needed (no real values)
├── .gitignore               ← keeps secrets, venv, cache and output off GitHub
├── requirements.txt         ← exact package versions
├── pytest.ini               ← tells pytest where the code and tests are
├── PROJECT_OVERVIEW.md      ← this file
├── credentials/
│   └── service_account.json ← Google robot-account key                 (git-ignored)
├── data/
│   └── catalog.csv          ← the company's product list (9 products)
├── emails/
│   └── email_01..05.txt     ← 5 sample emails, each testing a different case
├── src/
│   ├── extract_one.py       ← Gemini extraction (Order schema + prompt)
│   ├── validate.py          ← business rules
│   ├── sheets.py            ← Google Sheets writer
│   ├── run_pipeline.py      ← runs everything end to end
│   └── test_sheet.py        ← old Part 1 connection check (see section 10)
├── tests/
│   └── test_validate.py     ← 7 pytest tests for validate.py
└── output/                  ← created by the pipeline                  (git-ignored)
    ├── json/email_XX.json   ← cached Gemini answers
    └── orders.csv           ← all validated rows
```

## 6. The files and functions

### 6.1 `src/extract_one.py`: email text → structured Order

**Why this file exists:** it's the only place that talks to Gemini. If the LLM changes (another model or provider), only this file changes.

| Part | What it is | Why it's needed |
|---|---|---|
| `class OrderLine(BaseModel)` | one product line: `product`, `quantity`, `unit_price`, `currency` | defines exactly which fields a line has. `Optional` means a field may be `null` when it isn't in the email |
| `class Order(BaseModel)` | the whole email: `is_order`, sender name/company/email, `order_reference`, `order_date`, `lines: list[OrderLine]`, `notes` | one email can contain **many** lines, so lines is a list. `notes` lets Gemini explain *why* something is null |
| `SYSTEM_PROMPT` | the instructions for Gemini | sets the rules: only use what's written, never guess, null + note if unclear, convert words to numbers, unit price without the symbol, 3-letter currency, non-orders get `is_order=false` |
| `client = genai.Client(...)` | the Gemini connection, using `GEMINI_API_KEY` from `.env` | the key is never written in the code |
| `MODEL = "gemini-3.6-flash"` | which model to use | one constant, so it's easy to change |
| `extract_order(email_text) -> Order` | sends the email to Gemini and returns a pydantic `Order` | the core step. Uses `response_mime_type="application/json"` + `response_schema=Order` (**structured output**: Gemini has to answer in this exact shape) and `temperature=0` (as repeatable as possible, no creativity) |
| `if __name__ == "__main__":` block | `python src/extract_one.py emails/email_01.txt` prints one result | lets me test the LLM on a single email without running the whole pipeline |

### 6.2 `src/validate.py`: business rules

**Why this file exists:** an LLM can be wrong or leave gaps. These checks are exact, cost nothing, run instantly and can be tested. This file never reads the email. It trusts Gemini's `is_order` and checks the extracted values.

| Function | What it does | Why it's needed |
|---|---|---|
| `load_catalog(path) -> list[str]` | reads `data/catalog.csv` and returns the `product` column as a list | the catalog is the "source of truth" for product names. Keeping it in a CSV means the business can update it without touching code |
| `match_product(name, catalog)` | lowercases and strips the name, then finds the closest catalog name with `difflib.get_close_matches(..., cutoff=0.8)`, returning the **official** spelling or `None` | customers write `oud royale 100ml edp`, `Oud Royale 100ml`, etc. Matching maps them to one official name. `cutoff=0.8` allows small typos but rejects products that aren't in the catalog |
| `validate(df, catalog) -> DataFrame` | 1) `df.copy()`; 2) `pd.to_numeric(errors="coerce")` on quantity and price; 3) adds `catalog_product`; 4) adds `line_total = unit_price × quantity`; 5) applies the rules and builds an `issues` text column | turns raw extracted rows into checked rows. `copy()` avoids changing the caller's data. `coerce` turns bad values into NaN instead of crashing |

**The rules** (each one is a True/False mask over all rows):

| Rule | Flagged when | Example |
|---|---|---|
| `not_an_order` | `is_order` is False | email_05 (complaint) |
| `missing_price` | order and `unit_price` is empty | email_02 Saffron, email_03 "same prices as last month" |
| `bad_quantity` | order and quantity is empty or ≤ 0 | quantity 0 |
| `unknown_product` | order and no catalog match | email_04 "Travel Atomizer Set" (not in the catalog on purpose) |
| `missing_currency` | order, price present, currency empty | "185 each" with no currency |

Every rule except `not_an_order` starts with `is_order &`, so a non-order gets **exactly one** flag, not five. A row can collect several flags, e.g. `missing_price;unknown_product;`. An empty `issues` means the row is clean.

**Why a dict of rules + a loop:** adding a new rule is one new line in the dict, and the loop code never changes.

### 6.3 `src/sheets.py`: write a DataFrame to a Google Sheet tab

| Function | What it does | Why it's needed |
|---|---|---|
| `write_tab(sheet_id, tab_name, df)` | logs in with the service account, opens the sheet **by ID**, finds the tab or creates it, clears it, and writes the header + rows | one reusable function for any tab ("Clean", "Review", a future "Failed" tab) |

Details and reasons:
- **`open_by_key(sheet_id)`, not open by name:** the ID never changes and is unique, while names can be duplicated or renamed. Opening by name failed in Part 1 with `SpreadsheetNotFound`.
- **Create the tab if it's missing** (`try` / `except gspread.WorksheetNotFound`): works on a brand-new sheet with no manual setup. Only that one error is caught, so real errors (like no permission) still show.
- **`clear()` and then write:** running the pipeline twice gives the same sheet, not duplicate rows (**idempotent**).
- **`df.astype(object).where(df.notna(), "")`:** NaN isn't valid JSON, so the Sheets API rejects it. Empty cells are used instead.
- **`[columns] + values`:** row 1 is the header, then one list per data row, which is the format `update()` expects.

### 6.4 `src/run_pipeline.py`: runs everything end to end

**Why this file exists:** it's the coordinator. It holds no credentials and no business rules. It just moves data between the other modules.

| Part | What it does | Why it's needed |
|---|---|---|
| `EMAIL_DIR`, `CACHE_DIR`, `COLUMNS` | folder paths and the output column order | settings in one place. `COLUMNS` controls what the sheet shows and in which order |
| `get_order(email_path) -> Order` | if `output/json/<name>.json` exists, load it (`Order.model_validate_json`); otherwise call `extract_order`, save the JSON, wait 2 seconds | **cache:** each email costs one API call in total, re-runs are instant and free, and results don't change between runs. `sleep(2)` respects the free-tier rate limit. Failed emails aren't cached, so a re-run retries only those |
| `order_to_rows(order, source_file) -> list[dict]` | builds `base` (email-level fields), then returns one dict per line (`{**base, **line.model_dump()}`). If there are no lines, it returns one row with empty product fields | **flattening:** an Order is nested (1 email → many lines) but a sheet is flat (1 row per line). The no-lines branch keeps complaints in the output, otherwise they'd silently disappear. `source_file` lets every row be traced back to its email |
| `main()` | loads `.env`, loops over emails with a `try/except` per email, builds one DataFrame, validates, saves `output/orders.csv`, splits Clean/Review, writes both tabs, prints a summary | the `try/except` per email means one bad email (e.g. a 503 from Gemini) doesn't stop the batch, and the failed file names are printed at the end |

### 6.5 `tests/test_validate.py`: unit tests for the rules

**Why:** I can change the rules and know immediately whether something broke, and the tests make no API call (free, under 1 second, same result every time).

| Helper / test | Purpose |
|---|---|
| `CATALOG` | a small fixed catalog, so the tests don't depend on `data/catalog.csv` |
| `make_row(**changes)` | one valid base order line. Each test changes only the field it's testing, so a failure points to exactly one rule |
| `run(row)` | dict → 1-row DataFrame → `validate` → `.loc[0]` (the result row as a Series) |
| `test_clean_row_has_no_issues` | a valid row gets `issues == ""` |
| `test_missing_price_is_flagged` | `unit_price=None` gives `missing_price` |
| `test_zero_quantity_is_flagged` | `quantity=0` gives `bad_quantity` (an edge case: 0, not just missing) |
| `test_unknown_product_is_flagged` | a product not in the catalog gives `unknown_product` |
| `test_not_an_order_gets_only_one_flag` | a non-order gets **exactly** `"not_an_order;"` (checked with `==`, not `in`) |
| `test_close_name_matches_catalog` | extra spaces and lowercase still match the official name |
| `test_line_total` | 2 × 10.0 = 20.0 |

### 6.6 Config files

| File | Why |
|---|---|
| `pytest.ini` | `pythonpath = src` lets tests `import validate` directly. `testpaths = tests` tells pytest where to look |
| `.env` / `.env.example` | secrets live outside the code. `.example` shows others which keys to set, without the real values |
| `.gitignore` | keeps `.env`, `credentials/`, `.venv/`, `output/`, `__pycache__/` off GitHub |
| `requirements.txt` | exact versions, so the project installs the same way on any machine |
| `data/catalog.csv` | 9 products with category and list price. "Travel Atomizer Set" is left out **on purpose** to test `unknown_product` |

## 7. The test emails (each one covers a different case)

| Email | Case | Expected result |
|---|---|---|
| 01 | clean bullet-list PO in AED | 3 lines → all **Clean** |
| 02 | one price missing ("please confirm your current price") | Velvet Oud → Clean, Saffron → **Review** (`missing_price`) |
| 03 | quantities in words + "same prices as last month" | "two dozen" → 24, "fifty" → 50, both → **Review** (`missing_price`) |
| 04 | table, prices in USD, one product not in the catalog | 2 → Clean, Travel Atomizer Set → **Review** (`unknown_product`) |
| 05 | complaint, not an order | 1 row → **Review** (`not_an_order`) |
| **Total** | | **11 rows: 6 Clean, 5 Review** |

## 8. Results so far

- All 5 emails processed by `gemini-3.6-flash`, all exactly as expected (cached in `output/json/`):
  - 01: 3 lines, PO-2291, AED prices correct
  - 02: Saffron price `null`, with the note *"Unit price ... is missing and requires confirmation"*
  - 03: "two dozen" → 24, "fifty pieces" → 50, prices `null`, with the note *"Prices were set to null because the email mentions 'Same prices as last month'"*. That's the "never guess" rule working.
  - 04: USD table read correctly; Travel Atomizer Set flagged `unknown_product`
  - 05: complaint flagged `not_an_order`
  - Pipeline output: **11 rows, 6 Clean / 5 Review** ✅
- On the first attempt, emails 04-05 hit **503 UNAVAILABLE** (high demand) and one run hung with no reply (see limitations 1-2). A later re-run processed them; 01-03 came from the cache.
- Unit tests: **7 / 7 passing**.

## 9. How to run

From the project root (relative paths depend on it):

```powershell
cd order-automation
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

pytest -v                                          # 1. rules: expect 7 passed
python src/extract_one.py emails/email_01.txt      # 2. Gemini on one email
python src/run_pipeline.py                         # 3. full pipeline
```

One-time setup: a Gemini API key in `.env`, a Google Cloud service account with its key in `credentials/service_account.json`, and the Google Sheet shared with the service account's email as **Editor** and its ID in `.env` as `SHEET_ID`.

After changing the prompt or model, delete the cache: `Remove-Item output\json\*.json`.

## 10. Known limitations (and what I'd do next)

| # | Limitation | Why it matters | Fix |
|---|---|---|---|
| 1 | **No timeout on the Gemini call** | if the server stalls, the script waits forever (this happened) | `http_options=types.HttpOptions(timeout=60_000)` on the client |
| 2 | **No automatic retry** | a temporary 503 needs a manual re-run | `@retry` from `tenacity` with exponential backoff, ideally only for 503/429 |
| 3 | **Mixed currencies in Clean** | email_04's USD rows sit next to AED rows, so summing `line_total` gives a wrong number | flag non-AED as `foreign_currency`, or convert at a fixed rate |
| 4 | **The cache can go stale** | after a prompt or model change, old answers are still used | delete the cache, or store the model + prompt version in the cache file name |
| 5 | **Overwriting deletes human edits** | `clear()` wipes the tabs, so fixes typed into Review are lost on the next run | append new emails only and keep a list of processed IDs |
| 6 | **`is_order` depends on Gemini alone** | if Gemini calls a complaint an order, the rules can't catch it | spot-check outputs, and add a confidence field or a keyword cross-check |
| 7 | **Failures only shown in the terminal** | nobody watching the sheet sees them | write failed files to a "Failed" tab |
| 8 | **Only the rules are tested** | `order_to_rows` and the pipeline have no tests | test `order_to_rows` with fake Orders (0 lines → 1 row, 3 lines → 3 rows) and mock Gemini |
| 9 | **No price check against the catalog** | an email price far from the list price isn't noticed | rule: flag if `unit_price` differs from `list_price_aed` by more than X% |
| 10 | **Emails are local .txt files** | not connected to a real inbox | read from Gmail/Outlook (API or IMAP) on a schedule |
| 11 | **`src/test_sheet.py` is outdated** | it opens the sheet by name, which fails | delete it or switch it to `open_by_key` |

## 11. What this project shows (for interviews)

- **Using LLMs safely in a business process:** structured output + schema, temperature 0, a "never guess, null + explain" prompt, and a human review queue.
- **Splitting work between AI and code:** the LLM understands text, deterministic code does the numbers and rules.
- **Data cleaning and validation with pandas:** `to_numeric(errors="coerce")`, boolean masks, fuzzy matching against reference data.
- **Production habits:** caching, a per-item `try/except`, idempotent writes, secrets kept outside the code and out of git, pinned dependencies, unit tests.
- **Honest about limits:** a clear list of what breaks and how I'd fix it.

**30-second pitch:**
> "Trading companies get orders by email in every format, and someone retypes them by hand. I built a pipeline where Gemini turns each email into a fixed JSON schema and is told never to guess, so missing values come back as null with a note. pandas then cleans the data, matches products to the catalog, calculates totals and flags problems. Clean lines go to one Google Sheet tab and flagged ones to a Review tab for a person to check. I cache every LLM answer, handle failures per email, and the business rules are covered by pytest."
