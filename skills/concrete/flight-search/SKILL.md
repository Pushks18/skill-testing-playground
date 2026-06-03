# flight-search

## When to Use
When the user asks to find, search, or compare flights between two destinations.

## Workflow
1. Extract origin, destination, and travel date from user message
2. Call search_flights with extracted parameters
3. Present top 3 results sorted by price
4. Ask user if they want to book one

## When NOT to Use
- User is asking about hotel accommodations only
- User is asking about fare cancellation policies (use fare-rules instead)
