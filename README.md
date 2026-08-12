# Board Book Generator

Turns a freeform, plain-text meeting agenda into a finished board book PDF:

1. **Input parser** - Claude (structured outputs) converts freeform agenda text into
   structured JSON, and a deterministic time calculator assigns each item a
   sequential start time from the meeting's start time and item durations.
2. **Agenda template** - an HTML/CSS template replicating the University of
   Alberta GFC agenda format (logo + committee/date header, two-column
   time/item table) is rendered to a PDF cover page via headless Chromium.
3. **PDF compiler & stamper** - the cover page is merged with user-provided
   PDF attachments, placed sequentially after the agenda in agenda-item
   order (attachments can target a specific item *or* one of its sub-items,
   e.g. a single Consent Agenda motion), then every page of the final
   document is stamped with a global "Page X of Y" footer.

The committee is picked from a dropdown of the 9 GFC standing committees
(see `boardbook.committees`) instead of relying on the source text, and
every text role on the cover page (headings, item title, presenters, action
label, time column) has independently configurable font/size/weight via
`TemplateStyle` - see "Customizing the agenda template" below.

## Project layout

```
app.py                    Streamlit web UI (see "Web app" below)
setup.sh                  One-shot environment bootstrap (venv + deps + Chromium)
requirements.txt          Pinned fallback dependency set (see Troubleshooting)
src/boardbook/
  models.py            Domain models (Agenda, AgendaItem, AttachmentSpec, TemplateStyle, BuildRequest)
  committees.py        The 9 GFC standing committees, for the committee picker
  parser/
    schema.py           Pydantic schema Claude is asked to fill in
    claude_client.py     Anthropic structured-output call -> ExtractedAgenda
    time_calculator.py   ExtractedAgenda -> Agenda (adds item_number + calculated_time)
  template/
    agenda.html.j2        Jinja2 template for the GFC-style cover page
    styles.css             Print stylesheet (page size/margins, two-column layout)
    renderer.py            Jinja2 render + headless-Chromium HTML -> PDF
  compiler/
    merger.py               Cover PDF + attachments -> one PDF, in agenda item order
    stamper.py               Final pass: "Page X of Y" footer on every page
  pipeline.py             Wires the stages together (parse -> build)
  cli.py                  `boardbook parse|build|generate|doctor`
  api.py                  FastAPI service (`/parse`, `/attachments`, `/logo`, `/build`)
```

Each stage is independently importable - `parser`, `template`, and `compiler`
have no dependency on the CLI, API, or web UI, so you can call
`parse_text_to_agenda()` or `merge_board_book()` directly from your own code.
`app.py` and `cli.py` both call the exact same `boardbook.pipeline` functions.

## Setup

Requires Python 3.9+.

### Quick start

```bash
./setup.sh
```

Creates `.venv`, installs everything (including Streamlit), downloads headless
Chromium, and runs a full environment check at the end. Re-running it is safe.

### Manual setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Headless Chromium is used to render the agenda cover page (HTML/CSS -> PDF).
# This downloads a self-contained browser build - no system Cairo/Pango/etc.
# packages required.
playwright install chromium
```

Set your Anthropic credentials (either works - see the Claude API docs for
details):

```bash
cp .env.example .env
# then edit .env and set ANTHROPIC_API_KEY=...
```

or run `ant auth login` and leave `ANTHROPIC_API_KEY` unset. (The web UI also
accepts the key directly in its sidebar if you'd rather not set it as an
environment variable.)

**After setup, activate the venv in every new terminal** before running
`boardbook`, `streamlit`, `pytest`, etc.:

```bash
source .venv/bin/activate
```

This is the single most common source of "environment" errors -
`command not found: boardbook` and `ModuleNotFoundError: No module named
'boardbook'` both mean the venv isn't activated in the current shell.

Run `boardbook doctor` any time to check the environment (venv, dependencies,
headless Chromium, credentials) and get an exact fix for whatever's wrong:

```bash
$ boardbook doctor
Board Book Generator - environment check

Python: 3.9.6 (/path/to/.venv/bin/python3)
  [OK]   Python version is >= 3.9
  [OK]   Running inside a virtualenv (...)

Dependencies:
  [OK]   anthropic
  ...

Agenda rendering (Playwright + headless Chromium):
  [OK]   Headless Chromium launches successfully

Anthropic credentials:
  [OK]   ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN is set

0 failing, 0 warning(s).
Environment looks good.
```

### Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `command not found: boardbook` | venv not activated in this shell | `source .venv/bin/activate` |
| `ModuleNotFoundError: No module named 'boardbook'` | venv not activated, or package not installed | `source .venv/bin/activate && pip install -e ".[dev]"` |
| `Could not launch headless Chromium` | Playwright's browser binary was never downloaded | `playwright install chromium` |
| `AuthenticationError` / 401 when parsing | no/invalid Anthropic credentials | set `ANTHROPIC_API_KEY` in `.env`, run `ant auth login`, or paste the key into the web UI's sidebar |
| `pip install -e ".[dev]"` resolves to incompatible versions | dependency resolver picked a bad combination | `pip install -r requirements.txt && pip install -e . --no-deps` (a known-good pinned set) |
| `'_SpecialForm' object has no attribute 'replace'` when parsing | the venv's Python has a broken `typing` module (seen with an old python.org 3.9.0 build shadowing the system Python in `PATH`) - it crashes Pydantic's schema generation | recreate the venv with a different interpreter, e.g. `rm -rf .venv && PYTHON_BIN=/usr/bin/python3 ./setup.sh` (macOS: `/usr/bin/python3` is the Xcode-bundled build and is usually safe) |
| Anything else | unknown | `boardbook doctor` |

## Web app

```bash
streamlit run app.py
```

Opens at `http://localhost:8501`. Walks through the same three pipeline
stages as the CLI:

1. Pick the **committee** from a dropdown (the 9 GFC standing committees -
   this overrides whatever committee name Claude would otherwise extract
   from the text, so you don't have to spell it out consistently yourself),
   paste the raw agenda text, pick the meeting date, click **Parse Agenda**.
2. Review the extracted items - each item **and each of its sub-items**
   (e.g. individual Consent Agenda motions) gets its own drag-and-drop PDF
   uploader, so a supporting document can be attached to the exact entry it
   belongs to. An institution logo can be uploaded in the sidebar. An
   optional **Style settings** panel lets you set the font, size, and bold
   weight independently for each part of the cover page (the two header
   lines, item title, presenters, action label, and time column).
3. Click **Generate & Download Board Book PDF** to render, merge, and stamp
   the final document. It's previewed inline and downloadable immediately.

If `ANTHROPIC_API_KEY` isn't set in your environment, the sidebar has a
password-masked field to paste one in for the session instead.

## Deploying to the web (Streamlit Community Cloud)

This puts the app at a public (or invite-only) URL with **your** Anthropic
API key held server-side, so your users never need their own key or any
local setup - they just open a link.

**Files already in this repo that make this work:**

- `requirements.txt` - the pinned dependency set Streamlit Cloud installs.
- `packages.txt` - the Debian `apt` packages headless Chromium needs at
  runtime (Streamlit Cloud runs `apt-get install` on these automatically).
- `app.py`'s `_ensure_chromium_installed()` - Streamlit Cloud only ever runs
  `pip install -r requirements.txt`, never `playwright install chromium`, so
  the app downloads the browser binary itself on first launch (cached for
  the life of the container - later visitors don't pay this cost).

**Steps:**

1. Push this repo to GitHub (see below if it isn't one yet).
2. Go to [share.streamlit.io](https://share.streamlit.io), sign in, click
   **Create app**, and point it at your repo/branch with **main file path**
   `app.py`.
3. Open **Advanced settings** before deploying:
   - **Python version:** pick 3.11 or 3.12.
   - **Secrets:** add your key as a root-level TOML entry -
     ```toml
     ANTHROPIC_API_KEY = "sk-ant-..."
     ```
     Streamlit Cloud automatically exposes root-level secrets as environment
     variables, so no code change is needed - the app's existing
     `os.environ.get("ANTHROPIC_API_KEY")` check picks it up directly, every
     visitor sees "Anthropic API key detected," and the sidebar's "paste
     your own key" field never appears.
4. Click **Deploy**. The first build takes a few minutes (installing
   dependencies + apt packages); the first page load additionally waits
   ~30s for `_ensure_chromium_installed()`'s one-time browser download.

**If the build fails on a `packages.txt` line:** Debian occasionally renames
a package between releases (e.g. `libasound2` -> `libasound2t64`) faster than
this list can be verified against Streamlit Cloud's current base image -
the build log names the exact missing package; delete or rename that one
line and redeploy. Everything else here doesn't need to change.

**Multi-user safety:** a key pasted into the sidebar by an individual
visitor is used for that request only and is never written to a shared
location - see `parse_agenda_text`'s `api_key` parameter in
`src/boardbook/parser/claude_client.py`. Only your own server-side
`ANTHROPIC_API_KEY` secret is shared across visitors, which is the point.

**If this isn't a git repo / on GitHub yet:**

```bash
git init
git add .
git commit -m "Initial commit"
gh repo create YOUR-REPO-NAME --source=. --private --push   # needs the GitHub CLI (gh)
# or create an empty repo on github.com, then:
#   git remote add origin https://github.com/YOU/YOUR-REPO-NAME.git
#   git push -u origin main
```

Double-check `.gitignore` before pushing - it already excludes `.env`,
`uploads/`, and `output/`, but if you've been storing real institutional
data (uploaded logos, sample attachments) anywhere else in the tree, remove
it or add it to `.gitignore` first.

## CLI usage

Three entry points, matching the pipeline's stages:

```bash
# 1. Parse freeform text into structured JSON (with computed start times).
#    --committee overrides whatever committee name Claude would extract from the text.
boardbook parse examples/sample_agenda.txt -o agenda.json \
  --meeting-date 2026-09-15 \
  --committee "GFC Executive Committee"

# 2. Build the final PDF from that JSON, a logo, and any supporting documents.
#    --attachment is repeatable: "ITEM_NUMBER:PATH" attaches to the item itself;
#    "ITEM_NUMBER.SUB_NUMBER:PATH" (1-based) attaches to one of its sub-items -
#    e.g. one specific Consent Agenda motion. Order is preserved within each.
boardbook build \
  --agenda agenda.json \
  -o boardbook.pdf \
  --logo logos/university_crest.png \
  --attachment "4:attachments/academic_standing_policy_amendments.pdf" \
  --attachment "6.1:attachments/minutes_june_9.pdf" \
  --attachment "6.2:attachments/data_science_certificate_proposal.pdf" \
  --style style.json

# One-shot: parse + build in a single command
boardbook generate examples/sample_agenda.txt \
  -o boardbook.pdf \
  --meeting-date 2026-09-15 \
  --committee "GFC Executive Committee" \
  --logo logos/university_crest.png \
  --attachment "4:attachments/academic_standing_policy_amendments.pdf"
```

`--style` (on `build`/`generate`) points to a JSON file matching `TemplateStyle`
(see `boardbook.models.TemplateStyle`) - e.g.:

```json
{
  "item_title": {"font_family": "Georgia", "size_pt": 12, "bold": true},
  "item_action": {"font_family": "Roboto", "size_pt": 9, "bold": false}
}
```

Any role you omit keeps the GFC-format default. `font_family` accepts
`"Roboto"`, `"Arial"`, `"Georgia"`, or `"Times New Roman"` (or any raw CSS
font-family string).

Run `boardbook --help` (or `boardbook <command> --help`) for the full option list.

## API usage

```bash
uvicorn boardbook.api:app --reload
```

```bash
# 1. Parse. committee_name overrides whatever committee Claude would extract from the text.
curl -s http://localhost:8000/parse \
  -H "Content-Type: application/json" \
  -d '{"text": "...", "meeting_date": "2026-09-15", "committee_name": "GFC Executive Committee"}' \
  | tee parsed.json

# 2. Upload a logo and each attachment - each returns a file_id
curl -s -F "file=@logos/university_crest.png" http://localhost:8000/logo
curl -s -F "file=@attachments/enrolment_trends_report.pdf" http://localhost:8000/attachments

# 3. Build - references the agenda JSON from step 1 and the file_ids from step 2.
#    attachments[].sub_item_index (0-based, optional) targets a specific sub-item -
#    e.g. one Consent Agenda motion - instead of the item as a whole.
#    style (optional) overrides fonts/sizes per role - see TemplateStyle in models.py.
curl -s http://localhost:8000/build \
  -H "Content-Type: application/json" \
  -d '{
        "agenda": <agenda object from parsed.json>,
        "logo_file_id": "<file_id from /logo>",
        "attachments": [
          {"item_number": 5, "file_id": "<file_id from /attachments>"},
          {"item_number": 6, "sub_item_index": 0, "file_id": "<file_id of the first sub-items attachment>"}
        ],
        "style": {"item_title": {"font_family": "Georgia", "size_pt": 12, "bold": true}},
        "output_filename": "gfc_2026-09-15.pdf"
      }' \
  --output boardbook.pdf
```

Interactive docs are served at `http://localhost:8000/docs`.

## Customizing the agenda template

The layout in `agenda.html.j2` / `styles.css` was measured directly from
real University of Alberta GFC board books: a centered logo/header block,
a narrower (~5.15in) left-anchored two-column item table with a light-gray
divider above each top-level item, and indented sub-entries (e.g. individual
Consent Agenda motions) with no clock time of their own. Edit the CSS to
adjust proportions or a different committee's letterhead without touching
any Python. `renderer.py` keeps the PDF page geometry (`_PAGE_FORMAT`,
`_PAGE_MARGIN`) in sync with the `@page` rule in the stylesheet; update both
together if you change the page size.

**Fonts & sizes:** each text role on the cover page - the two header lines,
item title, presenters, action label, and time column - has its own
font/size/bold weight, controllable per-build via `TemplateStyle` (the web
UI's "Style settings" panel, the CLI's `--style path/to/style.json`, or the
API's `style` field on `/build`) without touching any CSS. Roboto is the
default and is embedded directly (self-hosted, base64 `@font-face`) from
`src/boardbook/template/fonts/`, so it renders identically regardless of
what's installed on the host machine - no internet access needed at render
time. `Arial`/`Georgia`/`Times New Roman` are also selectable but rely on
the renderer machine having them (or a suitable fallback); to add another
self-hosted option, drop `.ttf` file(s) into that folder, add an entry to
`FONT_CHOICES` in `models.py`, and reference it by name.

**Item hierarchy:** each `AgendaItem` may carry `sub_items` (see
`boardbook.models.AgendaSubItem`) - indented entries with no independent
schedule time, used for things like each motion inside a Consent Agenda item
or reference documents under a Terms of Reference item. A sub-item's title
renders bold only when it has its own `action_type`; otherwise it's regular
weight, matching the source documents.

## Tests

```bash
pytest
```

The test suite covers the time calculator, PDF merging/stamping (against
small synthetic PDFs generated on the fly), and the Claude client's
error handling - all without hitting the network or requiring a browser
install, so it runs the same in CI as it does locally.
