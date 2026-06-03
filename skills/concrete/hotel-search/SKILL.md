# hotel-search

## When to Use
When the user asks to find, search, or compare hotel accommodations. Triggers on phrases like "find hotels", "search hotels", "where to stay in", "hotel near", "accommodation in", "book a room in", "hotels available".

## Workflow
1. Extract the following from the user message:
   - `location`: city, neighborhood, or landmark (e.g. "downtown Seattle", "near LAX", "Miami Beach")
   - `check_in`: arrival date in YYYY-MM-DD format
   - `check_out`: departure date in YYYY-MM-DD format
   - `guests`: number of guests (default 1 if not mentioned)
2. If the user specifies a number of nights but no check-out date, compute check_out = check_in + N days.
3. Call `search_hotels` with all extracted parameters.
4. From the results, present top 3 options sorted by `price_per_night` ascending, including: hotel name, star rating, price per night.
5. Ask the user if they want to book one.

## Parameter extraction rules
- "next weekend" → check_in = next Saturday, check_out = next Sunday
- "3 nights starting July 1" → check_in = 2026-07-01, check_out = 2026-07-04
- "near [airport]" → use the airport's city as location
- Star rating filters ("4-star or higher") → note in response but pass full results; filter after retrieval

## When NOT to Use
- User is only asking about flights → use flight-search
- User wants to complete a booking with passenger/guest details → use book-itinerary
- User wants to modify or cancel an existing hotel booking
- User is asking about flight fare rules or cancellation policies
