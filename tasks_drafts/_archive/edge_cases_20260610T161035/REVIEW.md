# Review sheet — edge_cases

Change `KEEP` to `DROP` for any draft you reject, edit drafts in place as
needed, then run: `python -m eval.taskgen promote --domain edge_cases`
Only rows still marked KEEP are promoted. To APPROVE the whole sheet leave it as is.

| action | id | calibration | instruction (first 100 chars) | expected tools |
|---|---|---|---|---|
| KEEP | edge-mixed-117 | baseline-fail | Please verify if I can still reserve a seat on flight AB321 for March 10, 2026. | check_availability |
| KEEP | edge-mixed-118 | baseline-fail | Can you search for a flight from New York to Los Angeles on November 20, and then from Los Angeles t | search_flights |
| KEEP | edge-mixed-119 | baseline-fail | I need to cancel my hotel reservation under booking ID BK98563274. What is the refund policy? |  |
| KEEP | edge-mixed-120 | baseline-pass | Please find the rules and terms for flight number BA456. | get_fare_rules |
| KEEP | edge-mixed-121 | baseline-fail | Reserve a flight for Michael Adams from San Francisco to Boston on October 10, 2026, and pick a hote | create_booking, search_hotels |
| KEEP | edge-mixed-122 | baseline-pass | Could you retrieve the itinerary for my current booking ID BK11235813? | get_itinerary |
| KEEP | edge-mixed-123 | baseline-fail | Modify the passenger's name on booking ID BK55664488 to Jessica Lim. |  |
| KEEP | edge-mixed-124 | baseline-fail | Look for flights from Boston to Tokyo on January 15, 2026, and from Tokyo to Sydney on January 20, 2 | search_flights |
| KEEP | edge-mixed-125 | baseline-fail | Is there availability on flight NZ908 for April 5, 2026? | check_availability |
| KEEP | edge-mixed-126 | baseline-pass | Change my booking BK99887777 so that my check-in date at the hotel is August 15, 2026 and check-out  | modify_booking |
