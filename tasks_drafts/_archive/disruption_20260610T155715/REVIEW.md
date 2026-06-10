# Review sheet — disruption

Change `KEEP` to `DROP` for any draft you reject, edit drafts in place as
needed, then run: `python -m eval.taskgen promote --domain disruption`
Only rows still marked KEEP are promoted. To APPROVE the whole sheet leave it as is.

| action | id | calibration | instruction (first 100 chars) | expected tools |
|---|---|---|---|---|
| KEEP | disruption-141 | baseline-fail | I've just been informed that my flight from Denver to Chicago is delayed. Could you verify if I'm el |  |
| KEEP | disruption-142 | baseline-fail | My flight from Miami to Atlanta has been canceled and I desperately need to catch the earliest avail | search_flights, modify_booking |
| KEEP | disruption-143 | baseline-pass | I'm supposed to stay in a hotel in Rome, but my flight was canceled. Can you cancel my hotel booking |  |
| KEEP | disruption-144 | baseline-fail | Unfortunately, my flight from Lisbon to New York got delayed. What are the rules regarding delay com |  |
| KEEP | disruption-145 | baseline-pass | My flight from Seattle to Los Angeles is canceled. Can you find an alternative flight? I don't have  |  |
| KEEP | disruption-146 | baseline-fail | I need assistance rescheduling my flight to Amsterdam following a cancellation. My booking ID is BK5 | search_flights, modify_booking |
| KEEP | disruption-147 | baseline-fail | My flight connection from Paris to Rome was missed. Could you book the next available flight? My boo | search_flights, modify_booking |
| KEEP | disruption-148 | baseline-fail | The hotel I've booked in Sydney can no longer accommodate me due to an error. Could you find an alte |  |
| KEEP | disruption-149 | baseline-fail | I missed my flight from Houston to Orlando and need to reschedule. Booking ID is HO8T9Y6P. | search_flights, modify_booking |
| KEEP | disruption-150 | baseline-pass | I was supposed to fly from San Francisco, but it was overbooked. What compensation or alternatives d |  |
