# Review sheet — disruption

Change `KEEP` to `DROP` for any draft you reject, edit drafts in place as
needed, then run: `python -m eval.taskgen promote --domain disruption`
Only rows still marked KEEP are promoted. To APPROVE the whole sheet leave it as is.

| action | id | calibration | instruction (first 100 chars) | expected tools |
|---|---|---|---|---|
| KEEP | disruption-131 | baseline-fail | My flight from Vancouver to Toronto was canceled. Can you assist me in booking an alternative flight | search_flights, modify_booking |
| KEEP | disruption-132 | baseline-fail | I had a booking for a flight from Athens to Rome, but I've been informed it's canceled. I need to fi | search_flights, modify_booking |
| KEEP | disruption-133 | baseline-pass | My flight from Dallas to Kansas City has been delayed. Could you let me know how to find out if ther |  |
| KEEP | disruption-134 | baseline-pass | I'm unable to travel to my booked hotel in Tokyo due to a flight cancellation. Can you cancel the re | cancel_booking |
| KEEP | disruption-135 | baseline-fail | Hey, my flight was overbooked from New York to Boston. What are my options now? |  |
| KEEP | disruption-136 | baseline-pass | I'm not sure if I have entered my booking ID correctly. Can you verify my details for either BK2N9X8 | get_itinerary |
| KEEP | disruption-137 | baseline-pass | I've just learned my flight from Amsterdam to Berlin is delayed. How do I find out if I'm eligible f |  |
| KEEP | disruption-138 | baseline-fail | I need to switch my hotel reservation in Los Angeles for later dates due to a flight delay. Can you  | modify_booking |
| KEEP | disruption-139 | baseline-pass | Something came up, and I need to cancel my flight to San Francisco. I do not remember my booking ID. |  |
| KEEP | disruption-140 | baseline-fail | I'm at the airport, and my flight to Singapore has been canceled. Can you please help me find the ne |  |
