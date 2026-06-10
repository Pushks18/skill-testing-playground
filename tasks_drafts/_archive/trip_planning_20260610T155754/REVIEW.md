# Review sheet — trip_planning

Change `KEEP` to `DROP` for any draft you reject, edit drafts in place as
needed, then run: `python -m eval.taskgen promote --domain trip_planning`
Only rows still marked KEEP are promoted. To APPROVE the whole sheet leave it as is.

| action | id | calibration | instruction (first 100 chars) | expected tools |
|---|---|---|---|---|
| DROP | planning-101 | baseline-fail | I want to explore Australia starting in Sydney, then to Brisbane and Melbourne, starting January 15  | search_flights, search_hotels, create_booking |
| DROP | planning-102 | baseline-fail | I have a conference in Berlin on May 10, 2026. I'll be flying in from Madrid, need to arrive by May  | search_flights, create_booking |
| DROP | planning-103 | baseline-pass | Could you help me book a round trip from Toronto to Tokyo next March? Unsure about exact dates, but  |  |
| DROP | planning-104 | baseline-pass | Plan an affordable weekend getaway for two in the U.S. under $800 total for flights and hotel. Depar | search_flights, search_hotels |
| KEEP | planning-105 | baseline-fail | I'd like to plan a quick trip to San Francisco from Seattle. It would be a two-night stay sometime n | search_flights, search_hotels |
| KEEP | planning-106 | baseline-fail | I want to attend a wedding in Austin on 2026-04-15 and I'm flying in from Denver. Could you organize | search_flights, search_hotels |
| KEEP | planning-107 | baseline-fail | I want to book a trip from Toronto to Cancun. Leaving on 2026-11-25 and returning after a week. I ne |  |
| KEEP | planning-108 | baseline-pass | I need assistance planning a road trip to visit Nashville and Memphis for me and my partner. We'll l |  |
| KEEP | planning-109 | baseline-fail | Could you help me plan a vacation in Barcelona for a week, starting December 15, 2026? I’ll be flyin | search_flights, search_hotels |
| KEEP | planning-110 | baseline-pass | I’m planning a romantic surprise trip for my girlfriend to Paris from Chicago, departing anytime aft | search_flights, search_hotels |
| KEEP | planning-111 | baseline-fail | I'm considering a holiday to the Maldives from Riyadh, tentatively in June 2026 for maybe a week. Wh |  |
| KEEP | planning-112 | baseline-fail | I'm planning a leisure trip from New York City to San Diego. Departure is August 10, 2026, and retur | search_flights, search_hotels, add_ancillary |

## Near-duplicates auto-marked DROP

- planning-101 ≈ planning-101 (cos 1.0)
- planning-102 ≈ planning-102 (cos 1.0)
- planning-103 ≈ planning-103 (cos 1.0)
- planning-104 ≈ planning-104 (cos 1.0)
