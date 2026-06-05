# Review sheet — flight_search

Change `KEEP` to `DROP` for any draft you reject, edit drafts in place as
needed, then run: `python -m eval.taskgen promote --domain flight_search`
Only rows still marked KEEP are promoted. To APPROVE the whole sheet leave it as is.

| action | id | calibration | instruction (first 100 chars) | expected tools |
|---|---|---|---|---|
| KEEP | flight-search-101 | baseline-pass | Look for flights from ATL to LAS for a solo traveler on 2026-09-25. | search_flights |
| KEEP | flight-search-102 | baseline-fail | Please confirm the availability of any flights between HOU and PDX departing on 2026-10-12 and retur | check_availability |
| KEEP | flight-search-103 | baseline-pass | Find one-way flights from SEA to BOS for three travelers on 2026-08-03. | search_flights |
| KEEP | flight-search-104 | baseline-pass | I need to know all possible flights available between SFO to IAD for me and my colleague on 2026-10- | search_flights |
