# hotel-search

## When to Use
When the user asks to find, search, or compare hotel accommodations.

## Workflow
1. Extract location, check-in, check-out dates from user message
2. Call search_hotels with extracted parameters
3. Present top 3 results sorted by price per night
4. Ask user if they want to book one

## When NOT to Use
- User is asking about flights only
- User already has a hotel and wants to modify it (use modify-booking)
