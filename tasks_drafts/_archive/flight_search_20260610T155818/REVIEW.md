# Review sheet — flight_search

Change `KEEP` to `DROP` for any draft you reject, edit drafts in place as
needed, then run: `python -m eval.taskgen promote --domain flight_search`
Only rows still marked KEEP are promoted. To APPROVE the whole sheet leave it as is.

| action | id | calibration | instruction (first 100 chars) | expected tools |
|---|---|---|---|---|
| KEEP | flight-search-131 | baseline-fail | I'm looking for flights from BKK to SYD on a weekend in June 2026 but haven't settled on a specific  |  |
| KEEP | flight-search-132 | baseline-pass | I need a one-way ticket from ORD to MSP on 2026-07-17 for one person. Please get all available fligh | search_flights |
| KEEP | flight-search-133 | baseline-pass | Book a round-trip flight from SFO to BKK departing on 2026-10-08 and returning on 2026-10-22 for an  | search_flights |
| KEEP | flight-search-134 | baseline-pass | Find the earliest flights from YVR to SFO on 2026-05-15 for two passengers. | search_flights |
| KEEP | flight-search-135 | baseline-pass | Could you check flights going from BOS to MUC on 2026-09-01? I haven't decided how many tickets I ne |  |
| KEEP | flight-search-136 | baseline-pass | I want to fly from FCO to ATH on 2026-08-25 for one passenger. Could you provide the fare rules for  | search_flights, get_fare_rules |
| KEEP | flight-search-137 | baseline-fail | Check for flights from JFK to CUN on 2026-12-11. Please also arrange a hotel in Cancun for two guest | search_flights, search_hotels |
| KEEP | flight-search-138 | baseline-fail | Look for flights from DEL to SIN on any Tuesday in February 2026. I prefer the earliest flights avai |  |
| KEEP | flight-search-139 | baseline-pass | Could you find a morning flight from JNB to CPT on 2026-11-05 for two adults? Ensure to book the ear | search_flights |
| KEEP | flight-search-140 | baseline-fail | Arrange a direct flight for me from CDG to NRT on 2026-06-18. After confirming, also add extra bagga | search_flights, add_ancillary |
