---
name: disruption-handling
description: Handle disruption handling tasks. Auto-proposed from eval failure cluster in domain 'disruption'. Review and edit before merging.
license: Apache-2.0
metadata:
  author: travel-platform
  version: "0.1.0"
---

# Disruption Handling

## Workflow

1. **Confirm required inputs.** Ask for any missing required fields before proceeding. Many of the failed tasks are missing booking references (`BK3X9Z2A` or `BK4Y7A6B`), desired destination/origin, or the specific nature of the disruption (e.g., "flight got canceled" is clear, but "I need to check availability" is not specific enough to a disruption).
2. **Identify the type of disruption.** Determine if the disruption is a cancellation, delay, missed connection, or other event impacting a travel itinerary. This will inform the appropriate tools and information to retrieve (e.g., compensation rules are only applicable for certain disruptions).

If the user's request involves knowing compensation rules or policies, directly use tools to retrieve and provide these policies without additional questions unless specific critical details are missing.
3. **Retrieve booking details.** Use the provided booking reference or passenger details to look up the affected itinerary. If multiple booking references are provided, attempt to verify each one to find the correct booking.
4. **Evaluate rebooking options or alternative solutions.** Based on the disruption type and the traveler's stated needs (e.g., "rebooking a similar flight to Denver"), investigate available tools or knowledge bases to find appropriate solutions (e.g., alternative flights, compensation policies). This step was entirely missed in the `NO_TOOL_CALL` failures, as the agent didn't attempt to search for solutions.
5. **Present options to the user.** Clearly communicate the available rebooking options, compensation information, or other relevant details obtained in the previous step.

## Required Inputs

| Input          | Notes                                                                                                                              |
| :------------- | :--------------------------------------------------------------------------------------------------------------------------------- |
| `disruption_type`    | The specific type of travel disruption (e.g., "flight cancellation", "flight delay", "missed connection"). Cannot be generic. |
| `passenger_name` | The full name of the passenger associated with the booking.                                                                        |
| `contact_email_or_phone` | An email address or phone number associated with the booking. Essential for verification if booking reference is ambiguous or missing. |

## Optional Inputs

| Input             | Default                          |
| :---------------- | :------------------------------- |
| `booking_reference` | None                             |
| `origin_airport`  | None                             |
| `destination_airport` | None                             |
| `desired_rebooking_date` | Original departure date if available |

## Output

```json
{
  "outcome_summary": "string", // A concise summary of the disruption handling process and resolution.
  "proposed_solutions": [
    {
      "solution_type": "string", // e.g., "rebooking_option", "compensation_info", "alternative_transport"
      "details": "object" // Structured details specific to the solution type (e.g., new flight details for rebooking)
    }
  ],
  "agent_actions_taken": [
    {
      "tool_name": "string",
      "parameters_used": "object",
      "result_summary": "string"
    }
  ]
}
```

## Edge Cases and Quality Checks

*   **Ambiguous Booking References:** If multiple booking references are provided or the provided reference is invalid, the agent must ask for clarification or additional identifying information (e.g., full passenger name, contact details, flight number) before attempting any tool calls.
*   **Missing Disruption Type:** If the user's initial instruction does not clearly state the disruption (e.g., "I need to check availability"), the agent must prompt the user for more specific information to determine the `disruption_type`. The agent should not assume a disruption has occurred without explicit confirmation.
*   **Incomplete Rebooking Requests:** If a user requests rebooking but does not specify a desired destination or date, the agent must prompt for these details.
*   **Verification of Passenger Details:** Even if a booking reference is provided, if there's any ambiguity, the agent should attempt to verify `passenger_name` against the booking to prevent incorrect actions.
*   **No Available Solutions:** If after investigating, no suitable rebooking options or compensation information can be found, the agent must clearly state this to the user and explain why.

* **Direct Response Requirement for Compensation:** When asked directly about compensation policies, use the relevant tool to provide this information directly instead of seeking additional input from the user unless essential parameters are missing.
