# Review sheet — hotel_search

Change `KEEP` to `DROP` for any draft you reject, edit drafts in place as
needed, then run: `python -m eval.taskgen promote --domain hotel_search`
Only rows still marked KEEP are promoted. To APPROVE the whole sheet leave it as is.

| action | id | calibration | instruction (first 100 chars) | expected tools |
|---|---|---|---|---|
| KEEP | hotel-search-129 | baseline-pass | Could you help me find a good hotel in Venice with a view of the Grand Canal for June 15 to June 20, | search_hotels |
| KEEP | hotel-search-130 | baseline-pass | I'm organizing a conference in Brisbane. Can you look for hotels with meeting facilities available f | search_hotels |
| KEEP | hotel-search-131 | baseline-pass | Book me a hotel room in Seoul. I don't have specific dates yet, but I'll need to stay for about a we |  |
| KEEP | hotel-search-132 | baseline-fail | I need a hotel in Bangkok from September 10 to September 15, 2027, with a rooftop pool. Can you find | search_hotels, create_booking |
| KEEP | hotel-search-133 | baseline-pass | We're arriving in Amsterdam for a wedding on March 20, 2027, for 4 nights. Find any unique hotels wi | search_hotels |
| KEEP | hotel-search-134 | baseline-pass | Please find a room for four guests at a beach resort in Cancun from July 10 to July 14, 2027, ideall | search_hotels |
| KEEP | hotel-search-135 | baseline-pass | Look for budget hotel options in Toronto for one night on December 15, 2026, near the downtown area. | search_hotels |
| KEEP | hotel-search-136 | baseline-pass | I'd like to stay in a hotel in Zurich with easy access to public transport. My travel dates are Apri | search_hotels |
| KEEP | hotel-search-137 | baseline-pass | Could you search for a pet-friendly hotel in Atlanta for March 4 to March 7, 2027? | search_hotels |
| KEEP | hotel-search-138 | baseline-fail | I'm looking for a hotel in Madrid with gym facilities from January 2 to January 5, 2027. Can you pro | search_hotels, create_booking |
