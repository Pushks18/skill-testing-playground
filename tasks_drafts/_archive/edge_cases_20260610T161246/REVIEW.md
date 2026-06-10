# Review sheet — edge_cases

Change `KEEP` to `DROP` for any draft you reject, edit drafts in place as
needed, then run: `python -m eval.taskgen promote --domain edge_cases`
Only rows still marked KEEP are promoted. To APPROVE the whole sheet leave it as is.

| action | id | calibration | instruction (first 100 chars) | expected tools |
|---|---|---|---|---|
| KEEP | edge-mixed-127 | baseline-pass | Could you confirm if there are any flights available from Sydney to Manila on 2026-06-14? | search_flights |
| KEEP | edge-mixed-128 | baseline-pass | Please check if there are any available rooms at a hotel in Berlin for two guests from October 5th t | search_hotels |
| KEEP | edge-mixed-129 | baseline-pass | What are the fare conditions for flight LH7890? | get_fare_rules |
| KEEP | edge-mixed-130 | baseline-pass | I'd like to book a flight from New Delhi to Singapore on February 20, 2026. Could you also book a ho | search_flights, search_hotels |
| KEEP | edge-mixed-131 | baseline-pass | I need the details of my current itinerary for booking reference BK87456382 before making any change | get_itinerary |
| KEEP | edge-mixed-132 | baseline-fail | Could you verify if flight QF123 is available on March 15, 2026? | check_availability |
| KEEP | edge-mixed-133 | baseline-fail | Can you modify my reservation BK23123456 to include an additional baggage service? |  |
| KEEP | edge-mixed-134 | baseline-fail | I'd like to change my hotel booking with ID BK3472113 to include breakfasts. Could you make this adj |  |
| KEEP | edge-mixed-135 | baseline-pass | Find out if there's a flight from Dallas to Toronto on April 18th, 2026, and then book a hotel in To | search_flights, search_hotels |
| KEEP | edge-mixed-136 | baseline-fail | Can you cancel the entire reservation under booking number BK14151617 and let me know about any appl |  |
