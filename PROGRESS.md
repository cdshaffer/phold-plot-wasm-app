# SEA-PHAGES Approved Terms → phold Category Pipeline: Progress Notes

Context doc for both the human collaborator and any coding agent picking this
project up later. Written 2026-07-22.

## Status: resumed (2026-07-23)

Development had been paused for about 24 hours pending a discussion with the
maintainers of the other SEA-PHAGES tooling (PhagesDB, Phamerator, Pheona)
about whether the approved-terms parser (`scripts/sync_approved_terms.py` +
`data/approved_terms.csv`) should be pulled out of this repo and published as
its own standalone SEA-PHAGES tool, since it isn't specific to circos plots.

No one expressed interest in that window, so **the parser stays inside
SEAcircos and work is resuming.** Nothing about how it was built precludes
extracting it into its own repo later if a maintainer wants it — that option
stays open, it's just not blocking anything now.

## The long-term goal

Build a SEA-PHAGES-optimized fork/derivative of
[phold-plot-wasm-app](https://gbouras13.github.io/phold-plot-wasm-app/) — a
Pyodide/WASM tool that lets undergraduates in the SEA-PHAGES program generate
circos plots of their phage genomes from their own hand-curated functional
annotations, instead of from phold's own structural-homology output.

This requires a machine-readable cross-reference between:
- the SEA-PHAGES **approved annotation terms list** (a living Google Sheet
  maintained by SEA-PHAGES HQ, not the user — view-only access), and
- the small, fixed set of functional categories phold-plot-wasm-app colors
  genes by.

The original attempt at this cross-reference
([catagory_cross_reference.csv](catagory_cross_reference.csv)) is stale (built
against an older version of the approved terms list) and stores the term list
as an unstructured text blob per category — not something code can reliably
parse or diff against future sheet updates.

Longer-term aspiration (explicitly *not* being built now): get the SEA-PHAGES
committee to make the approved-terms list itself a structured artifact that
*generates* the human-readable Google Doc, rather than the other way around.
For now, assume the Google Sheet stays the authoritative, hand-edited source.

## What phold-plot-wasm-app actually uses (verified from source, not assumed)

Fetched and read the live `index.html` from the
`gbouras13/phold-plot-wasm-app` repo. It's Pyodide-based: a Python `data_dict`
buckets each CDS by substring-matching phold's own `/function` GenBank
qualifier text. The real category set is:

| code | legend label | note |
|---|---|---|
| `head` | Head & packaging | |
| `con` | Connector | |
| `tail` | Tail | |
| `dna` | DNA/RNA & nucleotide metabolism | |
| `moron` | Moron / AMG / host takeover | |
| `lysis` | Lysis | |
| `int` | Integration & excision | |
| `transcription` | Transcription Regulation | |
| `other` | Other Function | |
| `unk` | Unknown Function | |
| `acr_defense_vfdb_card` | VF / AMR / ACR / DF | only triggered by phold's own database-hit qualifiers (vfdb/card/acr/defensefinder) — not reachable from free-text terms |

**Decision made:** SEA category "Anti-Defense Systems" folds into the `moron`
bucket (matches PHROG's own convention for defense/AMG genes), rather than
trying to reach the special 11th bucket, since that bucket is structurally
tied to phold's own database-hit metadata, not to hand-assigned free text.

Also found (and should fix when building the mapping file): the existing
`catagory_cross_reference.csv` maps "Head-to-Tail Connector proteins" to
`head and packaging` and "Gene Regulation and DNA-Associated Proteins" to
`DNA, RNA and nucleotide metabolism` — both are plausibly better mapped to
`con` and `transcription` respectively, given the app actually has distinct
buckets for those.

## The approved-terms source, and how to fetch it without manual steps

The sheet is published at:
```
https://docs.google.com/spreadsheets/d/e/2PACX-1vToasuRfxx_yfLa9ECFN4_6okwNI_5AJGWZ3NCy53Gz0QfoNrhAQ48HnBuSD1hsrY0zUTTn6EP3MGK_/pubhtml?gid=0&single=true
```

That `pubhtml` URL itself is a JS single-page app (no server-rendered table —
can't be scraped with plain HTTP). But swapping `pubhtml` for `pub` and adding
an `output=` param gives two plain, unauthenticated, script-fetchable exports
of the *same* published sheet:

- `.../pub?gid=0&single=true&output=csv` — cell values, all 6 columns
  (confirmed byte-identical to a manual "Download CSV")
- `.../pub?gid=0&single=true&output=pdf` — same content, but with font
  size/weight/color preserved (confirmed byte-identical to a manual PDF export)

This matters because **the CSV alone can't tell a category header apart from
an approved term** — everything is flattened to plain rows with no row-type
field. The PDF's formatting is the only reliable signal for that, and it
turns out to be a small, consistent, well-defined set of styles across the
whole document (validated against all 5 pages, not just a sample):

| row type | column-A style | count in current sheet |
|---|---|---|
| Top-level SEA category | bold, size ≈3.6, blue | 22 |
| Sub-category, "refinement" | bold, size ≈2.6 (same size as terms), **orange** | 40 |
| Sub-category, "morphotype" | bold, size ≈3.1, **blue** | 3 (Siphovirus/Myovirus/Podovirus Tail Structures) |
| Instructional note | italic | 5 |
| Approved term | plain weight, black/dark, any body font | 268 |
| Sheet's own header row | bold, size 2.6, black ("Function Name"/"USE") | 2 (skipped) |

Per the user, the two sub-category styles mean different things to a student:
- **"refinement" (orange)** — narrows the parent category, applies to any
  phage regardless of morphotype (e.g. "Replication Initiation and
  Elongation" under "DNA Replication").
- **"morphotype" (blue, smaller)** — mutually exclusive alternatives; a
  student should pick terms from *only* the one sub-category matching their
  phage's actual morphotype (Siphovirus vs Myovirus vs Podovirus tail
  structures).

## The pipeline: [scripts/sync_approved_terms.py](scripts/sync_approved_terms.py)

1. Fetches both exports into `data/raw/` (cached; `--refresh` re-downloads).
2. Extracts every column-A PDF text span (all 5 pages, in reading order) and
   classifies it into one of the row types above by font weight/style/size/
   color-hue.
3. Aligns the classified PDF row-sequence against the raw CSV row-sequence by
   matching column-A text in document order. Two real PDF-export quirks had
   to be handled here (both discovered by the alignment step erroring out
   during development, not anticipated in advance):
   - **Print-area clipping** — very long cells get visually truncated in the
     PDF. Accepted when the PDF text is a clean prefix of the CSV cell; the
     full CSV text is used in the output, and it's logged as a "truncation
     note," not an error.
   - **Line wrapping** — extremely long cells can wrap across multiple PDF
     spans. The aligner re-joins up to 5 consecutive spans, but *only* while
     doing so keeps the accumulated text a valid prefix of the known CSV
     cell — the merge is justified by matching ground truth, not by guessing
     from pixel coordinates (which vary across pages).
4. Walks the aligned sequence tracking current category / sub-category (+
   kind) / most recent instructional note, and emits one row per actual
   approved term to **[data/approved_terms.csv](data/approved_terms.csv)**
   with columns: `sea_category, sea_category_notes, sea_subcategory,
   sea_subcategory_kind, sea_subcategory_notes, preceding_instruction, term,
   notes, example_gene, publications, case_studies, deprecated_synonyms,
   source_row`.
5. Prints a QA summary every run: row-type counts, any truncation notes, and
   a heuristic warning for suspiciously long/sentence-like "term" entries
   (>8 words) that were probably meant to be instructional notes but weren't
   italicized.

**Design principle (explicitly requested by the user):** the sheet is
hand-edited by non-programmers and its formatting conventions could drift
without warning. Rather than guess when a style doesn't match one of the
known patterns, the parser raises `FormatDriftError` and stops, so a human
notices and updates the code — it does not try to be clever about
unrecognized cases.

### Current validated output

- 268 approved terms, 22 top-level categories (same 22 names, same order, as
  the existing `catagory_cross_reference.csv` — good cross-check that the
  extraction is correct), 43 sub-category instances (41 distinct names: 40
  "refinement" + 3 "morphotype"), 5 instructional notes.
- **Resolved:** the two mis-formatted instructional rows noted below (CSV rows
  164 and 385) have been italicized by the sheet's author and now correctly
  parse as `instruction` rows — verified they no longer appear as `term`
  values anywhere in the output, and that they correctly attach as
  `preceding_instruction` context to the terms that follow them in their
  section (the thymine-hypermodification note → its 5 system-part terms; the
  "OK to use general assignments" note → the 5 general terms it licenses). The
  fresh run produced zero format-drift errors, zero truncation notes, and zero
  "suspiciously long term" warnings.
- That same author edit had a side effect: the sheet's own "Function Name"
  header cell picked up italic formatting too (`Arial-BoldItalicMT`), which
  correctly tripped the bold+italic drift guard, since that combination had
  never appeared before. Fixed in `classify_span` by recognizing the sheet's
  fixed header labels ("Function Name"/"USE") by their known literal text
  *before* applying the style rules — safe because that row is discarded
  either way regardless of formatting, and it doesn't weaken drift-detection
  for actual data rows.
- The `deprecated_synonyms` column ("Do NOT use") is a mix of genuinely
  renamed/deprecated term names and just "don't confuse this with X"
  cautionary notes. Worth remembering for future rename-detection logic —
  should surface proposed matches for human confirmation, not auto-apply them.

### Re-running this yourself, without opening Claude Code

For when the sheet changes and you just want a fresh `approved_terms.csv`,
without starting claude.app or asking an agent to do it:

1. Open Terminal (Applications → Utilities → Terminal, or Spotlight → "Terminal").
2. Go to the project folder:
   ```bash
   cd "/Users/chris/Documents/192_genomes/SEAcircos"
   ```
3. Activate the project's Python virtual environment (already set up, with
   `pymupdf` already installed — no `pip install` needed):
   ```bash
   source .venv/bin/activate
   ```
   The prompt should now start with `(.venv)`.
4. Run the sync script, forcing a fresh download of the live sheet:
   ```bash
   python3 scripts/sync_approved_terms.py --refresh
   ```
   (Drop `--refresh` to re-parse the already-downloaded copy in `data/raw/`
   without hitting the network — useful if you just want to re-run the parser
   itself, e.g. after a code change, against the same source snapshot.)
5. Read the printed output:
   - `Wrote .../data/approved_terms.csv` plus row-type counts = success. The
     file is ready to use/commit as-is.
   - A `NOTE: ... clipped in the PDF export` line is informational, not an
     error — a very long cell was truncated in the PDF but the full text was
     still recovered from the CSV.
   - A `WARNING: ... look unusually long/sentence-like` line means some term
     is suspiciously long and might actually be an un-italicized instructional
     note (like the two fixed earlier) — worth flagging to the sheet's
     maintainers, but the script still finished and wrote a valid file.
   - `FORMAT DRIFT DETECTED — refusing to guess: ...` (script exits with an
     error, `data/approved_terms.csv` is left untouched from before) means the
     sheet's formatting changed in a way the parser doesn't recognize yet.
     That's the point to bring the error message back to Claude Code (or paste
     it into a chat) to get the parser updated — don't hand-edit
     `approved_terms.csv` to work around it.
6. When done: `deactivate` to leave the virtual environment.

## Not yet built — next steps

1. **`sea_category` → phold category-code mapping file.** Small, hand-curated,
   rarely-changing table (unlike `approved_terms.csv`, which regenerates from
   the live sheet). Seed from `catagory_cross_reference.csv`'s existing
   mapping, fixing the `con`/`transcription` mismatches noted above.
2. **A build/join step** producing the final `term → phold_category_code`
   lookup artifact the WASM app actually consumes.
3. **A diff/reconciliation script** for when the sheet changes again: compare
   a fresh `approved_terms.csv` against the last committed version, exact-match
   unchanged terms, propose (not auto-apply) renames via
   `deprecated_synonyms`, and flag brand-new or orphaned categories/terms for
   manual review.
4. **Full vs. short category labels (new requirement, not yet implemented).**
   Every category needs both a "full" name (identical to the approved-terms
   list, any length) and a "short" name (≤20 characters) for tight graphical
   spaces (legends, small plot regions). `catagory_cross_reference.csv` column
   B ("SEA Short names") already has short names for the older 23-category
   version — these need to be reconciled against the current 22-category list
   (names/order have already been confirmed to match closely; a few short
   names may need adding/renaming) rather than invented from scratch.
5. **User-selectable display granularity in the final app (new requirement,
   not yet implemented).** The user wants students to be able to choose, at
   runtime, which category scheme the plot uses:
   - (a) the full 22 top-level SEA categories (maximum biological detail),
   - (b) the ≤20-character short-name version of those same 22 categories
     (same granularity, compact labels), or
   - (c) the condensed ~10-category phold/PHROG scheme (matches the original
     phold-plot-wasm-app's legend and coloring).

   **Implication for schema/build design:** don't collapse category
   information down to just one final lookup early. Every term ultimately
   needs its full category name, short category name, *and* phold-bucket
   mapping simultaneously available, so the app can switch schemes without
   re-deriving anything.

## The app phase: three selectable classification systems

Reviewed 2026-07-23. The eventual SEA-PHAGES fork of phold-plot-wasm-app
should let a user pick, at runtime, which of three classification systems
colors the genes in the plot:

1. **Phold's own 11 categories** (`head`, `con`, `tail`, `dna`, `moron`,
   `lysis`, `int`, `transcription`, `other`, `unk`, `acr_defense_vfdb_card`) —
   exact hex colors already confirmed from the app's source (e.g. `head` /
   "Head & packaging" ≈ rgb(215,50,140) i.e. `#ff008d`; see the table earlier
   in this doc for the full set).
2. **The 22 top-level SEA-PHAGES categories** (`approved_terms.csv` ×
   `sea_category`).
3. **The 43 SEA-PHAGES sub-categories** (`sea_category` × `sea_subcategory`,
   40 "refinement" + 3 "morphotype").

This replaces the earlier plan of only building one final `term →
phold_category_code` lookup — the build step needs to keep full category
name, short category name, and phold-bucket mapping simultaneously available
per term (per the "user-selectable display granularity" note added earlier),
now generalized to all three systems above rather than just "full vs. short."

**Open design question, explicitly not solved yet: what colors to use for the
22- and 43-category systems.** Phold's 11 colors are fixed/known. The user's
instinct is to use those as a *basis* rather than invent an unrelated palette
from scratch — e.g. every SEA category/sub-category would inherit the hue of
whichever phold category it's cross-referenced to (via
`catagory_cross_reference.csv` column 3), varying lightness/saturation to
distinguish siblings that share a parent hue. This is a reasonable, standard
approach (hue-preserving palette expansion) but the actual palette still needs
to be designed and checked for legibility/accessibility at 22 and 43 swatches
— not yet done.

`catagory_cross_reference.csv` is the seed for this: column 1 is the 22
SEA categories (already confirmed to match `approved_terms.csv` exactly),
column 2 is a hand-picked short name for graphical use (≤20 chars, addresses
the earlier "full vs. short label" requirement), column 3 is the user's own
best-guess mapping to a PHROG/phold category. That mapping still has the
`con`/`transcription` mismatches noted earlier in this doc to fix, and needs
a fourth column added for the sub-category level (43 rows) once the top-level
mapping is confirmed.

## Starting point for the app phase: fork and run the unmodified baseline

Decided 2026-07-23: before changing any code, fork
[gbouras13/phold-plot-wasm-app](https://github.com/gbouras13/phold-plot-wasm-app)
to the user's own GitHub account, clone it locally, and confirm it runs as-is
in a browser on the user's Mac (using the sample `data/NC_043029_phold_output.gbk`
already in that repo). Deliberately validates the unmodified baseline —
confirms Pyodide/WASM works locally, gets the git/GitHub workflow set up —
before any SEA-PHAGES-specific changes are made.

**Done 2026-07-24.** User forked the app to
[github.com/cdshaffer/phold-plot-wasm-app](https://github.com/cdshaffer/phold-plot-wasm-app).
Before merging anything, validated the *unmodified* fork actually runs: served
it locally (`python3 -m http.server`), opened it in a browser, clicked the
built-in "Example" button, and confirmed via console logs and the DOM that
Pyodide installed micropip/biopython/pycirclize and produced a real
3440×4773px plot with a working download link. Baseline confirmed working on
this Mac before touching any code.

Then merged: copied the fork's tracked files (`index.html`, `styles.css`,
`README.md`, `data/NC_043029_phold_output.gbk`,
`.github/workflows/static.yml` — no filename collisions with anything already
in SEAcircos) into this directory, transplanted the fork's `.git` history in
directly (rather than losing it and starting fresh), and added `upstream`
pointing at `gbouras13/phold-plot-wasm-app` alongside `origin` (the user's
fork) — so future updates from the original project can still be pulled in
with `git fetch upstream` / `git merge upstream/main`. Re-served the merged
directory and re-confirmed the app still loads correctly. Nothing has been
committed yet (SEAcircos's own files — `scripts/`, `data/approved_terms.csv`,
`PROGRESS.md`, `catagory_cross_reference.csv`, `requirements.txt`, `.gitignore`,
`CLAUDE.md` — currently sit untracked, staged for the user to review and
commit when ready).

**Decided 2026-07-24: unify.** The forked app becomes part of this same
SEAcircos repo rather than a separate one, since the long-term goal is tight
integration between the always-updating approved-terms list and the generated
figures, and the parser's still-open "maybe split out later" future stays
available regardless (a git-history split is easy to do later if it's ever
needed; going the other direction — merging two independent repos — is more
work than staying unified from the start). The fork will be cloned so its git
history and `upstream` remote (pointing at `gbouras13/phold-plot-wasm-app`)
are preserved, then this repo's existing files (scripts/, data/, PROGRESS.md,
etc.) get added into that same working directory.

### Repo housekeeping (2026-07-24)

Before pushing anything public, cleaned up the project folder:
- Added `.gitignore`: `.venv/`, `.DS_Store`, `*.swp`, `~$*` (Office lock
  files), `data/raw/` (regenerable fetch cache), `__pycache__/`, and
  `.claude/settings.local.json` (machine-local Claude Code permissions).
- Moved personal/non-deliverable files out of the project folder entirely,
  into a new sibling folder `../SEAcircos-personal/`: `sea_functions.xlsx`
  (personal cross-referencing notes), `personal_notes.md`, `SEA-PHAGES
  Bioinformatics Technical Report.md` (background reading), and the
  originally manually-downloaded `SEA-PHAGES FUNCTIONAL ASSIGNMENTS -
  Sheet1.csv`/`.pdf` at the repo root (redundant now that
  `scripts/sync_approved_terms.py` fetches its own copies into the
  gitignored `data/raw/`).

## Key files

| File | What it is |
|---|---|
| `scripts/sync_approved_terms.py` | fetch + classify + align pipeline (done) |
| `data/raw/sheet1.csv`, `data/raw/sheet1.pdf` | fetched source artifacts (regenerated by the script) |
| `data/approved_terms.csv` | canonical normalized output (done) |
| `catagory_cross_reference.csv` | old/stale category→phold mapping + short names; source for next step, needs updating (currently open/being edited in MacVim by the user) |
| `requirements.txt` | pins `pymupdf` (only dependency beyond stdlib) |
| `.gitignore` | excludes `.venv/`, `data/raw/`, OS/editor cruft, local Claude settings |
| `../SEAcircos-personal/` (sibling folder, outside this repo) | `sea_functions.xlsx`, `personal_notes.md`, the Bioinformatics Technical Report, and the original manually-downloaded Sheet1 CSV/PDF — personal, not project deliverables |
