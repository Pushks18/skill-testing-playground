# Review sheet — flight_search

Change `KEEP` to `DROP` for any draft you reject, edit drafts in place as
needed, then run: `python -m eval.taskgen promote --domain flight_search`
Only rows still marked KEEP are promoted. To APPROVE the whole sheet leave it as is.

| action | id | calibration | instruction (first 100 chars) | expected tools |
|---|---|---|---|---|
| KEEP | flight-search-140 | baseline-fail | Check flights from LGW to MAD on any Thursday in April 2026. |  |
| KEEP | flight-search-141 | baseline-pass | I need a flight from MIA to LAX on 2026-09-29 for one passenger. Can you also find the fare rules fo | search_flights, get_fare_rules |
| KEEP | flight-search-142 | baseline-pass | Search for the most affordable flights going from OSL to BOD on 2026-08-11. | search_flights |
| KEEP | flight-search-143 | baseline-pass | I'm planning a trip from SFO to DUB on 2026-11-07. Will you arrange round-trip flights and check for | search_flights, search_hotels |
| KEEP | flight-search-144 | baseline-fail | Please let me know the flight options from AKL to CHC for one person on a weekday in March 2026. I n |  |
