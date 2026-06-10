# Review sheet — hotel_search

Change `KEEP` to `DROP` for any draft you reject, edit drafts in place as
needed, then run: `python -m eval.taskgen promote --domain hotel_search`
Only rows still marked KEEP are promoted. To APPROVE the whole sheet leave it as is.

| action | id | calibration | instruction (first 100 chars) | expected tools |
|---|---|---|---|---|
| KEEP | hotel-search-119 | baseline-pass | I'm interested in staying at a hotel in Bali with ocean views from May 5 to May 10, 2027. Can you fi | search_hotels |
| KEEP | hotel-search-120 | baseline-pass | Find a pet-friendly hotel in Nashville from November 1 to November 3, 2026, for one person. | search_hotels |
| KEEP | hotel-search-121 | baseline-fail | We're looking for budget accommodations for 3 nights in Reykjavik, checking in July 22. What options | search_hotels |
| KEEP | hotel-search-122 | baseline-pass | Could you find a hotel in Dubai with an airport shuttle service from September 15 to September 20, 2 | search_hotels |
| KEEP | hotel-search-123 | baseline-pass | I need a hotel with a kitchen and gym in Berlin from March 5 to March 9, 2027. Can you check availab |  |
| KEEP | hotel-search-124 | baseline-fail | What hotels are available in Chicago for the weekend of April 2, 2027? I want to compare my options. |  |
| KEEP | hotel-search-125 | baseline-fail | I'm planning a honeymoon in Kyoto. Could you find romantic hotels available from June 10 to June 15, | search_hotels |
| KEEP | hotel-search-126 | baseline-pass | Book a hotel room for one night in Miami. I don't have the exact dates yet. |  |
| KEEP | hotel-search-127 | baseline-pass | We want to stay in a family-friendly hotel in Orlando from December 22 to December 27, 2026. What ar | search_hotels |
| KEEP | hotel-search-128 | baseline-fail | Please find accommodation in Lisbon for my work trip from February 5 to February 10, 2027. I'll also | search_hotels |
