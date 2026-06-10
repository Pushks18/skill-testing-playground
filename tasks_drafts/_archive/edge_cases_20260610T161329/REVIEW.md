# Review sheet — edge_cases

Change `KEEP` to `DROP` for any draft you reject, edit drafts in place as
needed, then run: `python -m eval.taskgen promote --domain edge_cases`
Only rows still marked KEEP are promoted. To APPROVE the whole sheet leave it as is.

| action | id | calibration | instruction (first 100 chars) | expected tools |
|---|---|---|---|---|
| KEEP | edge-mixed-137 | baseline-fail | Please see if flight AF789 is available on December 5, 2026. | check_availability |
| KEEP | edge-mixed-138 | baseline-pass | I'd like to reschedule my flight booking BK11235877 to July 22, 2026. Can this be arranged? | modify_booking |
| KEEP | edge-mixed-139 | baseline-fail | Could you help me find flights from New York to Rome on May 12th, 2026? Also, look for hotels in Rom | search_flights, search_hotels |
| KEEP | edge-mixed-140 | baseline-pass | I need to check my booking details for reservation number BK78451236 before making a change. Can you | get_itinerary |
