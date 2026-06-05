# Review sheet — trip_planning

Change `KEEP` to `DROP` for any draft you reject, edit drafts in place as
needed, then run: `python -m eval.taskgen promote --domain trip_planning`
Only rows still marked KEEP are promoted. To APPROVE the whole sheet leave it as is.

| action | id | calibration | instruction (first 100 chars) | expected tools |
|---|---|---|---|---|
| KEEP | planning-101 | baseline-fail | I want to explore Australia starting in Sydney, then to Brisbane and Melbourne, starting January 15  | search_flights, search_hotels, create_booking |
| KEEP | planning-102 | baseline-fail | I have a conference in Berlin on May 10, 2026. I'll be flying in from Madrid, need to arrive by May  | search_flights, create_booking |
| KEEP | planning-103 | baseline-fail | Could you help me book a round trip from Toronto to Tokyo next March? Unsure about exact dates, but  |  |
| KEEP | planning-104 | baseline-pass | Plan an affordable weekend getaway for two in the U.S. under $800 total for flights and hotel. Depar | search_flights, search_hotels |
