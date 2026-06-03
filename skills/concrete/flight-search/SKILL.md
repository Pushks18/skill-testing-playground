# flight-search

## When to Use
When the user asks to find, search, or compare flights between two cities or airports. Triggers on phrases like "find flights", "search flights", "what flights are available", "cheapest flight to", "fly from X to Y", "flights on [date]", "one-way/roundtrip to".

## Workflow
1. Extract the following from the user message:
   - `origin`: departure city or airport code (e.g. "New York" → "JFK", "Chicago" → "ORD")
   - `destination`: arrival city or airport code
   - `date`: travel date in YYYY-MM-DD format. If the user says "next Monday" or another relative date, compute the actual date based on today.
   - `passengers`: number of passengers (default 1 if not mentioned)
2. Call `search_flights` with all extracted parameters.
3. From the results, identify the top 3 options sorted by `price` ascending.
4. Present each option with: airline, departure time, duration, price.
5. Ask the user if they want to book one of the options.

## Parameter extraction rules
- Airport codes: JFK=New York, LAX=Los Angeles, ORD=Chicago, SFO=San Francisco, MIA=Miami, BOS=Boston, SEA=Seattle, DEN=Denver, PHX=Phoenix, ORD=Chicago, MIA=Miami, DFW=Dallas
- If only city name given, use the primary airport code for that city
- For roundtrip requests: call `search_flights` twice — once for outbound, once for return
- For multi-leg trips: call `search_flights` once per leg in sequence
- If date is relative ("next Monday", "this weekend", "tomorrow"), resolve to YYYY-MM-DD before calling the tool

## When NOT to Use
- User is only asking about hotel accommodations → use hotel-search
- User is asking about cancellation fees, baggage rules, or fare conditions → use fare-rules
- User wants to complete a booking with passenger details → use book-itinerary
- User wants to modify or cancel an existing booking
