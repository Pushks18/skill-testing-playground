# Review sheet — trip_planning

Change `KEEP` to `DROP` for any draft you reject, edit drafts in place as
needed, then run: `python -m eval.taskgen promote --domain trip_planning`
Only rows still marked KEEP are promoted. To APPROVE the whole sheet leave it as is.

| action | id | calibration | instruction (first 100 chars) | expected tools |
|---|---|---|---|---|
| KEEP | planning-142 | baseline-fail | I plan to travel from Dallas to Vancouver for a conference on March 15, 2026, but I haven't booked m |  |
| KEEP | planning-143 | baseline-fail | My cousin is getting married in Lisbon next May, and I need to fly from New York. Can you organize t | search_flights, create_booking, search_hotels |
| KEEP | planning-144 | baseline-fail | Arrange a spa day addition for my booking ID AB7F5G1H. | add_ancillary |
| KEEP | planning-145 | baseline-fail | I'm looking to attend a music festival in Melbourne with friends for four nights. We're coming from  | search_flights, create_booking, search_hotels |
| KEEP | planning-146 | baseline-pass | I want to schedule a family getaway to the Bahamas for a week, starting next June. We'll be travelin |  |
| KEEP | planning-147 | baseline-fail | I need to travel from Los Angeles to Beijing for business on June 10, 2026. Can you book a hotel nea | search_flights, create_booking, search_hotels |
