# Review sheet — flight_search

Change `KEEP` to `DROP` for any draft you reject, edit drafts in place as
needed, then run: `python -m eval.taskgen promote --domain flight_search`
Only rows still marked KEEP are promoted. To APPROVE the whole sheet leave it as is.

| action | id | calibration | instruction (first 100 chars) | expected tools |
|---|---|---|---|---|
| DROP | flight-search-101 | baseline-pass | Look for flights from ATL to LAS for a solo traveler on 2026-09-25. | search_flights |
| DROP | flight-search-102 | baseline-fail | Please confirm the availability of any flights between HOU and PDX departing on 2026-10-12 and retur | check_availability |
| DROP | flight-search-103 | baseline-pass | Find one-way flights from SEA to BOS for three travelers on 2026-08-03. | search_flights |
| DROP | flight-search-104 | baseline-pass | I need to know all possible flights available between SFO to IAD for me and my colleague on 2026-10- | search_flights |
| KEEP | flight-search-105 | baseline-pass | Can you check for any available flights from LAX to BOS on 2026-09-20? I'm planning for two passenge | search_flights |
| KEEP | flight-search-106 | baseline-pass | I'm eyeing a round trip from DEN to MCO, flying out 2026-11-03 and back on 2026-11-10. Before I comm | check_availability |
| KEEP | flight-search-107 | baseline-pass | I'm putting together a multi-city trip: New York JFK to London LHR on 2026-09-02, then London LHR to | search_flights |
| KEEP | flight-search-108 | baseline-pass | Please search for flights departing from MIA to EWR on 2026-07-25. Additionally, I need a hotel in N | search_flights, search_hotels |
| KEEP | flight-search-109 | baseline-fail | Could you find flights from SEA to LAX available on a Monday in September 2026? I haven't decided on |  |
| KEEP | flight-search-110 | baseline-pass | Check for a one-way flight from DFW to JFK for one passenger on 2026-08-15, and then let me know the | search_flights, get_fare_rules |

## Near-duplicates auto-marked DROP

- flight-search-101 ≈ flight-search-101 (cos 1.0)
- flight-search-102 ≈ flight-search-102 (cos 1.0)
- flight-search-103 ≈ flight-search-103 (cos 1.0)
- flight-search-104 ≈ flight-search-104 (cos 1.0)

## DROP reasons (reviewer)

- flight-search-101: already promoted to tasks/ on Jun 5 — draft is a byte-identical
  leftover of the promoted copy (dedupe cos 1.0 against its twin in tasks/).
- flight-search-102: same — already promoted (the bank's baseline-fail
  check_availability round-trip case lives in tasks/flight-search-102).
- flight-search-103: same — already promoted.
- flight-search-104: same — already promoted.

## Reviewer edits

- flight-search-106 rewritten in place: the generated draft ("most affordable
  options ATL→ORD") was the weakest of the batch — a near-rehash of the plain
  one-city searches (101/105) with no distinguishing tool surface. Replaced with
  a round-trip check_availability case (DEN↔MCO, explicit resource ids FL204 /
  FL451) so the promoted six retain check_availability coverage. validate,
  dedupe, and calibrate were re-run after the edit (calibration.json reflects
  the edited draft).

## KEEP rationale (the promoted six)

- 105: plain search, paraphrase family with promoted 101 (baseline-pass)
- 106: round-trip check_availability with explicit resource ids (baseline-pass)
- 107: multi-leg/multi-city, sequential search_flights (baseline-pass)
- 108: cross-tool flight+hotel combo (baseline-pass)
- 109: missing-info llm_judge — must ask for the date, not act (baseline-fail)
- 110: multi-step search_flights → get_fare_rules (baseline-pass)
