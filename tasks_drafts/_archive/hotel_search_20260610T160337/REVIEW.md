# Review sheet — hotel_search

Change `KEEP` to `DROP` for any draft you reject, edit drafts in place as
needed, then run: `python -m eval.taskgen promote --domain hotel_search`
Only rows still marked KEEP are promoted. To APPROVE the whole sheet leave it as is.

| action | id | calibration | instruction (first 100 chars) | expected tools |
|---|---|---|---|---|
| KEEP | hotel-search-109 | baseline-pass | Can you check availability for hotels in Nashville from September 25 to September 29 for 3 adults? | search_hotels |
| KEEP | hotel-search-110 | baseline-pass | I'm planning a trip to Barcelona. Could you find hotels available from 2026-07-18 to 2026-07-21? | search_hotels |
| KEEP | hotel-search-111 | baseline-pass | I want to stay in a beachfront hotel in Malibu from October 12 to October 15. What's available? | search_hotels |
| KEEP | hotel-search-112 | baseline-pass | Book a hotel in Dallas. I don't have the dates yet. |  |
| KEEP | hotel-search-113 | baseline-pass | I need two connecting rooms in Cancun. We'll be arriving from August 5 to August 10. What's out ther | search_hotels |
| KEEP | hotel-search-114 | baseline-fail | Can you find a hotel in Prague with a spa and on-site restaurant from 2026-09-10 to 2026-09-14? |  |
| KEEP | hotel-search-115 | baseline-pass | Please search for a convention center hotel in Denver for August 25 to August 28. | search_hotels |
| KEEP | hotel-search-116 | baseline-fail | What hotels in Key West are available for four nights with check-in on December 18 for 4 guests? Boo | search_hotels, create_booking |
| KEEP | hotel-search-117 | baseline-pass | Find me a hotel with free breakfast in New Orleans from November 14 to November 16 for one person. | search_hotels |
| KEEP | hotel-search-118 | baseline-pass | I want to compare hotels with conference facilities in Singapore from January 10 to January 14, 2027 | search_hotels |
