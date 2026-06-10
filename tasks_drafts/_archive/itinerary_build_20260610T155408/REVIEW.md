# Review sheet — itinerary_build

Change `KEEP` to `DROP` for any draft you reject, edit drafts in place as
needed, then run: `python -m eval.taskgen promote --domain itinerary_build`
Only rows still marked KEEP are promoted. To APPROVE the whole sheet leave it as is.

| action | id | calibration | instruction (first 100 chars) | expected tools |
|---|---|---|---|---|
| KEEP | itinerary-133 | baseline-pass | Could you plan a week-long visit to Rio de Janeiro, starting with flights from Lisbon and accommodat | search_flights, search_hotels |
| KEEP | itinerary-134 | baseline-fail | I'm thinking of a spontaneous getaway to Bali. Can you find flights from Jakarta for next weekend? |  |
| KEEP | itinerary-135 | baseline-fail | Please organize a 5-day trip to Buenos Aires. I'll be flying from Toronto, and I'd like a hotel in t | search_flights, search_hotels |
| KEEP | itinerary-136 | baseline-pass | I'm curious about the details of my booking under the reference BK1D2F3G. | get_itinerary |
| KEEP | itinerary-137 | baseline-fail | Plan a short trip to Cairo, with flights from Istanbul. Can you book a hotel near the Pyramids? | search_flights, search_hotels |
| KEEP | itinerary-138 | baseline-pass | What are my travel plans for the reference number BK2Z5Y8W? | get_itinerary |
| KEEP | itinerary-139 | baseline-fail | Could you arrange a festive holiday in New Orleans, including flights from Dallas and a hotel with a | search_flights, search_hotels |
| KEEP | itinerary-140 | baseline-fail | I want to visit Dubai over the winter break. Can you find some flight options from Cape Town? |  |
| KEEP | itinerary-141 | baseline-fail | Organize a honeymoon trip to Bora Bora with flights from San Francisco. We'll need a resort booking  | search_flights, search_hotels |
| KEEP | itinerary-142 | baseline-pass | Could you put together a relaxing 4-day spa retreat in Phuket, starting with a flight from Singapore | search_flights, search_hotels |
