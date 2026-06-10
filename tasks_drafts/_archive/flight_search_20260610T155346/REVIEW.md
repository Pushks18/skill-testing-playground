# Review sheet — flight_search

Change `KEEP` to `DROP` for any draft you reject, edit drafts in place as
needed, then run: `python -m eval.taskgen promote --domain flight_search`
Only rows still marked KEEP are promoted. To APPROVE the whole sheet leave it as is.

| action | id | calibration | instruction (first 100 chars) | expected tools |
|---|---|---|---|---|
| KEEP | flight-search-111 | baseline-pass | Find me flights from SFO to LAX for two adults on October 5, 2026. I need these flights to arrive in | search_flights |
| KEEP | flight-search-112 | baseline-pass | I need flight options from ATL to DFW for a trip on 2026-09-14 for four people. | search_flights |
| KEEP | flight-search-113 | baseline-pass | I need a round trip from JFK to CDG, departing 2026-10-01 and returning 2026-10-08 for 1 adult. Also | search_flights, search_hotels |
| KEEP | flight-search-114 | baseline-pass | What flights are available from MIA to BOS for one traveler flying on 2026-08-18? | search_flights |
| KEEP | flight-search-115 | baseline-fail | Search for flights from BOS to SFO on February 15, 2026. I am not sure how many passengers yet. |  |
| KEEP | flight-search-116 | baseline-pass | I’m looking for flights from LAS to ORD on 2026-09-30 for two adults. Could you find any? | search_flights |
| KEEP | flight-search-117 | baseline-fail | Please book me a flight from LHR to JFK on 2026-12-24. Also, find a hotel in New York City for the s | search_flights, search_hotels |
| KEEP | flight-search-118 | baseline-pass | Are there flight options from IAD to MCO for November 4, 2026, for three individuals? | search_flights |
| KEEP | flight-search-119 | baseline-fail | Can you find flights operating between DUB and LAX on a Sunday in November 2026? I don't have an exa |  |
| KEEP | flight-search-120 | baseline-pass | Please check for flights from SYD to HNL, departing 2026-12-15 for four passengers. Then, provide th | search_flights, get_fare_rules |
