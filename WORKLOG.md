# MIU Trace Worklog

Last updated: 2026-08-24 (Asia/Seoul)

## 2026-08-24 — First-confirmed timeline display and PWA icon

- Range-precision events now use the audit archive's exact `최초 확인` timestamp as the primary timeline date when it exists. The source-date limitation remains visible as `원장상 추정 기간`, so the page does not present a monthly-snapshot estimate as a fabricated event date.
- The same first-confirmed timestamp is the ordering key for those range events. This makes multiple price changes deterministic in date/time order instead of relying on ambiguous monthly range starts.
- Added the MIU Trace home-screen icon: a pale-gray field with a black footprint trail and lower-left magnifier. It is wired into the web manifest, browser favicon, Apple touch icon, and updated service-worker cache.
- Refined the icon to match the GitHub-inspired MIU Trace palette (`#f6f8fa`, graphite, restrained blue). Footprints and magnifier now have deliberately subtle 3D depth while remaining legible at small home-screen sizes.

## Beta update — Public Google Sheets

- Public CSV profiling completed for all 20 supplied worksheets.
- Google movement parser reads the event header (date, route, quantity) and vertical barcode cells.
- Google price parser reads date columns, barcode cells and adjacent price cells.
- Generated 27 real supporting events for the three known-answer barcodes with zero worksheet errors.
- GitHub Pages now reads `frontend/data/beta-events.json`, not the old hard-coded demo, for `C24306`, `HK30034`, and `YH25032085`.
- Each event links back to its source spreadsheet and reports `DATE/HIGH`; no exact time is invented.
- GitHub Actions refreshes the public beta index every six hours and on manual dispatch.
- Still pending: authoritative Dropbox receiving/sales/refund events and the full Oracle-hosted index API.
- Beta API prepared for `automation-runner` as an isolated systemd service on `127.0.0.1:8010`, with a six-hour Google sync timer.

Observed beta counts:

- `C24306`: 7 Google location events
- `HK30034`: 7 Google location events + 1 price event (`2026-07-24`, `30,000`)
- `YH25032085`: 11 Google location events + 1 price event (`2026-08-03`, `58,000`)

The supplied movement worksheet list ends at `26/04`. Expected May/July/August 2026 movement records and second-level timestamps were not present in the public CSV views, so they remain explicitly missing rather than inferred.

## Current release

- Repository: `https://github.com/leehk2275/miu-trace`
- Pages: `https://leehk2275.github.io/miu-trace/`
- Stage: live full-beta product-history service
- Deployment: Oracle `automation-runner` source sync → generated public index → GitHub Pages

## Completed

- Independent `miu-trace` repository and GitHub Pages workflow
- Installable responsive PWA shell
- GitHub-inspired barcode search and chronological timeline UI
- Source Authority domain rules for official receiving and finalized/current sales
- Five Google spreadsheet IDs registered in `config/sources.yaml`
- Barcode normalization and coverage-bound current-period fallback rules
- Static `C24304` demo timeline

## Confirmed integration gap

The deployed page is currently in `DEMO_MODE`. Google Sheets and Dropbox are not queried yet. The five Google spreadsheet IDs are configuration only; there is no credentialed adapter, worksheet profiler, parser, database indexer, evidence merger, or deployed timeline API. Therefore intermediate Google Sheets events cannot appear in the current UI.

## Beta milestones

### B1 — Source Profiler

- Connect five Google Sheets read-only
- Discover every worksheet title, gid, headers, sample value types and barcode/date candidates
- Profile Dropbox workbook sheets without creating production events
- Store reports under `reports/` with secrets and raw sensitive values excluded

### B2 — Lineage database

- Raw Source → Raw Record → Observation → Event → Event Evidence
- SQLite locally; PostgreSQL-compatible schema for hosted beta
- Parser profile/version and source revision tracking

### B3 — Google supporting evidence

- Normalize barcode and timestamps
- Parse explicit price/location/status/operation changes
- Never create official `RECEIVED` from Google Sheets alone
- Attach Google rows as evidence to matching authoritative events
- Preserve distinct intermediate events when time/type/value differs

### B4 — Dropbox authority parsers

- `공동판매_auto / 입고`: official receiving, product snapshots, location/price/status changes
- `전매장매입매출_auto용_수빈 / 매출`: finalized sales/refunds
- `공동판매_auto / 전매장매출`: uncovered-period fallback only

### B5 — Beta API and live UI

- Private FastAPI timeline API
- Pages frontend points to API through `API_BASE_URL`
- CORS restricted to the Pages origin
- No source credentials or private keys in GitHub/Pages
- Source Diagnostics reports real scan/index status

### B6 — Acceptance test

- Select 3–10 known barcodes with expected intermediate events
- Compare every timeline item to its original source row
- Verify deduplication, authority, confidence and time precision
- Record false positives, omissions and `NEEDS_REVIEW` profiles

## Commit policy

Each completed milestone is committed independently to `main` while the beta is being assembled. Secrets, service-account JSON, Dropbox tokens and raw company data are never committed.

## 2026-08-11 Dropbox audit

- Scanned the three requested barcodes across the monthly `입고`, `전매장매출`, and annual `매출` workbooks.
- Monthly `입고` rows are rolling product snapshots and must not be emitted as repeated timeline events.
- `HK30034` appears in the 2026 sales authority with a positive transaction and a later `-1` reversal; these rows require transaction-aware pairing before publication.
- Google Sheets events remain date-precision records. The beta does not invent times that are absent from the source.
- Raw workbooks and Dropbox credentials remain outside the repository.

## Full beta integration

- Added recursive Dropbox workbook discovery and revision-aware local caching.
- Added authority-aware parsing for official receiving, finalized sales/refunds, and uncovered-period sales fallback.
- Added monthly snapshot comparison for ranged location, price, status, and product-information changes.
- Added a SQLite barcode index so arbitrary product lookups do not load or expose the complete company dataset.
- Added live per-barcode Google Sheets evidence lookup, current product state, details, event counts, and Korean summary output.
- Added an HTTPS reverse proxy deployment for the Oracle `automation-runner`; Dropbox credentials and the full index remain server-side.

## 2026-08-20 — Latest sales sync, status reconciliation, and audit archive

### What is live

- The live site is the transferred repository's Pages address: `https://leehk2275.github.io/miu-trace/`. The former `i7444636` Pages address returns 404 because the repository was transferred; it is not the current deployment target.
- The Oracle `automation-runner` host runs `miu-trace-beta.service` and `miu-trace-sync.timer`. The timer now refreshes once an hour.
- The refresh flow is Dropbox source files → Google Sheets supporting records → append-only event archive → public static index → GitHub Pages. Source credentials, deploy keys, full workbook data, and the private SQLite index stay on the server and are not committed.
- The public-index publisher uses a fresh temporary checkout and commits only generated public index files. This avoids publishing from an old/dirty server checkout.
- The exporter was changed to process barcode shards rather than one memory-heavy job. This recovered stable syncs on the Oracle host; a completed full run is approximately a few minutes instead of exhausting the instance.

### Latest-source inspection and correction

- Confirmed the latest common-sales workbook is `/공동판매_auto/2026/8월/2026.08_공동판매.xlsx`, modified 2026-08-20 13:05:57 KST (6.23 MB at inspection time).
- Its `전매장매출` worksheet contains records through 2026-08-19. A public-index verification barcode from that date (`C29711`) was emitted as `SOLD`.
- Corrected the coverage metadata bug: `sales_coverage_end` previously considered only the confirmed annual sales workbook. Common-sales fallback records were indexed but did not advance that public coverage value. The published coverage now reaches 2026-08-19.
- For the reported 8/19 paste, 306 entered rows became 301 searched barcodes because `PB2` appeared six times. The bulk screen now shows both numbers explicitly (for example, `입력 306건 · 중복 제외 301개`) rather than making the intentional duplicate removal look like a missing result.
- Browser fetching of generated index files now bypasses a stale static cache. This prevents a newly deployed data index from being hidden behind the prior `app.js` cache setting.

### Sales, refunds, and prefixes

- Barcode normalization trims whitespace and uppercases the value; the `WW`, `WWA`, and `SB` prefixes are supported and do not take a separate parser path. Investigation of representative `WW`/`SB` barcodes showed that their incorrect `보유중` display was a status/refresh issue, not a prefix-recognition issue.
- Finalized official-store sales are read from `전매장매입매출… / 매출` using date column C, barcode column E, and quantity column H. Common-sales fallback rows are read from `공동판매_auto / 전매장매출` using date column B, barcode column D, and quantity column G.
- A positive quantity creates a `SOLD` event; a negative quantity creates a `REFUND` event. Zero, absent, or invalid quantities are rejected rather than treated as sales.
- Current status is determined from the latest valid transaction ordered by date, source file, and row: latest sale means `판매됨`; latest refund means `보유`; a current `폐기` location overrides both. This replaces the old incorrect rule that treated any historical sale with no separately detected refund as final.
- Therefore a barcode can retain both sale and refund events in its timeline. A refund does not erase the sale; it returns the current-state result to `보유` unless a later transaction changes it again.

### Event archive (append-only audit ledger)

- Added `backend/app/event_archive.py` and `scripts/archive_events.py`. The server archive is SQLite at `/opt/miu-trace/var/event-archive.sqlite` and is deliberately outside Git and the public site.
- On its first completed run, the archive recorded 784,430 observed candidate events. Its stable SHA-256 fingerprint includes barcode, event type/time/value, and source-evidence identity.
- The archive is append-only: a later source scan can add a newly observed event but does not rewrite or remove an already archived one. Current Dropbox and Google events are preferred for normal display; archived copies are used when the original source record later disappears.
- Timeline evidence now shows `감사 보관됨 · 최초 확인 <time>` for retained events. For example, the 2026-08-19 sale event for `WW1002` was confirmed with first-seen time 2026-08-20 15:27 KST.
- This protects events that have been observed since the archive started, including sales later removed from a rolling workbook or Dropbox revision history. It cannot reconstruct events deleted before the first archive scan, cannot infer a sale from a workbook that never receives it, and cannot capture an event that appears and disappears wholly between hourly scans.
- Archive and UI marker assertions pass (`event archive assertions passed`, `archive marking assertions passed`). Generated static data was also optimized to prefer current source events over duplicate archived copies, reducing the public index back to about 18 MB.

### Timeline and product-history corrections delivered during this period

- Corrected authoritative location-change dates, including the reported `SB2509881` final move. Exact source dates are used when a dated ledger row exists; a range is only used where source snapshots provide no exact transition date.
- Timeline output now retains field-level before/after values for product changes, marks unavailable source values as `정보 누락/복원 가능성`, removes the unnecessary sequence number, simplifies official receiving to the received location, and derives the previous known price for price-change events where evidence exists.
- Category display removes operational prefixes such as `온`.
- The UI supports both one-barcode detail search and bulk search with expandable per-barcode results. Status chips such as `판매됨` and `보유` use distinct colors for faster scanning.

### Verification and deployment record

- Recent functional commits include latest common-sales coverage, duplicate-count clarification, transaction-aware sales/refund status, append-only archive ingestion, archive marking, and audit evidence display.
- GitHub Pages deployments for these commits completed successfully. The service and hourly timer were also verified active after recovery.
- The production design remains evidence-first: the page exposes only derived barcode timelines and source descriptions, while raw workbooks, tokens, Dropbox credentials, SSH/deploy-key material, and full private indexes remain untracked.
