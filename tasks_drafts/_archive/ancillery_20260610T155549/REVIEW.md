# Review sheet — ancillery

Change `KEEP` to `DROP` for any draft you reject, edit drafts in place as
needed, then run: `python -m eval.taskgen promote --domain ancillery`
Only rows still marked KEEP are promoted. To APPROVE the whole sheet leave it as is.

| action | id | calibration | instruction (first 100 chars) | expected tools |
|---|---|---|---|---|
| KEEP | ancillery-111 | baseline-pass | I'd like to add an extra baggage allowance of 20kg for my booking BK5H8R9K to Berlin. | add_ancillary |
| KEEP | ancillery-112 | baseline-pass | Could you book a wheelchair service for booking BK9K3M2L at Vienna airport? | add_ancillary |
| KEEP | ancillery-113 | baseline-fail | For my trip under booking BK4M7Q3C, I want lounge access in Singapore. What are the available option |  |
| KEEP | ancillery-114 | baseline-pass | Please ensure there's a kosher meal arranged for reference BK2N8R1V. | add_ancillary |
| KEEP | ancillery-115 | baseline-fail | I need updates on possible upgrades for booking BK1Q8P7Z. Please confirm if it's an option. |  |
| KEEP | ancillery-116 | baseline-fail | For booking BK0A2D4F, can you arrange a helicopter transfer from Nice airport to Monaco? |  |
| KEEP | ancillery-117 | baseline-pass | I've just booked a flight to Madrid with reference BK3U5T8N. Can you add travel insurance and a wind | add_ancillary |
| KEEP | ancillery-118 | baseline-pass | For my booking BK6G7Z2K, I need to add both a special meal and an expedited security check at the de | add_ancillary |
| KEEP | ancillery-119 | baseline-pass | I have a reservation BK4L6H3J. I need to arrange a child seat in the rental car for our trip to Los  | add_ancillary |
| KEEP | ancillery-120 | baseline-pass | Please include a Wi-Fi package for booking BK7C4F6M on my flight to Seoul. | add_ancillary |
