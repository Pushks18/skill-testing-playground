# Review sheet — edge_cases

Change `KEEP` to `DROP` for any draft you reject, edit drafts in place as
needed, then run: `python -m eval.taskgen promote --domain edge_cases`
Only rows still marked KEEP are promoted. To APPROVE the whole sheet leave it as is.

| action | id | calibration | instruction (first 100 chars) | expected tools |
|---|---|---|---|---|
| KEEP | edge-mixed-107 | baseline-fail | Check availability for a flight MR1735 on 2026-08-20. Is there space available? | check_availability |
| KEEP | edge-mixed-108 | baseline-pass | Can you cancel my current reservation BK3X9Z2A? | cancel_booking |
| KEEP | edge-mixed-109 | baseline-fail | I need to change the hotel dates on booking BK5Y8Z9K7 to September 5th to 10th, 2026. |  |
| KEEP | edge-mixed-110 | baseline-fail | Book a flight from Boston to Nashville on May 1st, 2026, for David Miller. Also, find and add a hote | search_flights, create_booking, search_hotels |
| KEEP | edge-mixed-111 | baseline-pass | What's the process to modify a booking? I might need to change my reservation BK22334455. |  |
| KEEP | edge-mixed-112 | baseline-fail | I need a flight from Seattle to Dallas on June 10th and Dallas to Miami on June 15th. Are there flig | search_flights |
| KEEP | edge-mixed-113 | baseline-pass | Modify my booking BK78234599 so that I now depart on July 12th, 2026. | modify_booking |
| KEEP | edge-mixed-114 | baseline-fail | I’m looking to book a flight from Chicago to Denver on December 21st, with Emily Brown as the passen | search_flights, create_booking |
| KEEP | edge-mixed-115 | baseline-pass | Can you find the fare rules for flight JL4567? | get_fare_rules |
| KEEP | edge-mixed-116 | baseline-pass | I want to look up my itinerary for booking BK9Y7T6R5 before making changes. | get_itinerary |
