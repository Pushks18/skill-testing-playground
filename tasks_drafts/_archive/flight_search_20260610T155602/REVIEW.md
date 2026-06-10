# Review sheet — flight_search

Change `KEEP` to `DROP` for any draft you reject, edit drafts in place as
needed, then run: `python -m eval.taskgen promote --domain flight_search`
Only rows still marked KEEP are promoted. To APPROVE the whole sheet leave it as is.

| action | id | calibration | instruction (first 100 chars) | expected tools |
|---|---|---|---|---|
| KEEP | flight-search-121 | baseline-pass | Please look up a one-way flight from CHI to ATL on 2026-10-10 for me and my spouse. Also, fetch the  | search_flights, get_fare_rules |
| KEEP | flight-search-122 | baseline-pass | I'm planning a trip from SLC to LAS for two people on 2026-09-12. What are my options? | search_flights |
| KEEP | flight-search-123 | baseline-pass | Can you find me a round-trip flight from ORD to MEX, leaving on 2026-10-15 and coming back a week la | search_flights, get_fare_rules |
| KEEP | flight-search-124 | baseline-fail | I'm looking to fly from LAX to SYD on any Saturday in March 2026. Could you help me with available f |  |
| KEEP | flight-search-125 | baseline-pass | Please arrange for a direct flight from DFW to JFK for two adults on 2026-10-25. Then check the avai | search_flights, search_hotels |
| KEEP | flight-search-126 | baseline-pass | Find me flights from BOS to DUB on 2026-12-18 for one passenger. I also need a full itinerary for bo | search_flights, get_itinerary |
| KEEP | flight-search-127 | baseline-fail | I'd like to know the earliest flights possible from PHX to SFO on 2026-11-02. | search_flights |
| KEEP | flight-search-128 | baseline-fail | Can you verify any flight options from MIA to SFO on a Friday in June 2026? |  |
| KEEP | flight-search-129 | baseline-fail | Find a flight from HEL to ARN on 2026-10-22. Then, if possible, add extra luggage service to a booki | search_flights, add_ancillary |
| KEEP | flight-search-130 | baseline-fail | Please search for flights from BNE to NRT departing on 2026-08-05. Also, check for the possibility o | search_flights, modify_booking |
