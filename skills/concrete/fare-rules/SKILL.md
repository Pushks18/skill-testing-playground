# fare-rules

## When to Use
When user asks about cancellation policies, change fees, refunds, or baggage rules for a flight.

## Workflow
1. Identify the flight_id from context or ask the user
2. Call get_fare_rules with the flight_id
3. Summarize cancellation, change, and baggage rules in plain language

## When NOT to Use
- User wants to search for new flights
- User wants to book or modify a booking
