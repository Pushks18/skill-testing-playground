# Review sheet — hotel_search

Change `KEEP` to `DROP` for any draft you reject, edit drafts in place as
needed, then run: `python -m eval.taskgen promote --domain hotel_search`
Only rows still marked KEEP are promoted. To APPROVE the whole sheet leave it as is.

| action | id | calibration | instruction (first 100 chars) | expected tools |
|---|---|---|---|---|
| KEEP | hotel-search-101 | baseline-pass | I'm planning a trip to Rome and need a hotel from 2026-07-05 to 2026-07-10 with a view of the Coloss | search_hotels |
| DROP | hotel-search-102 | baseline-pass | Can you help me find accommodation in Barcelona for three guests from August 10th to August 15th? | search_hotels |
| KEEP | hotel-search-103 | baseline-pass | I need a 5-star hotel in Sydney for a business trip. The stay is from 2026-11-01 to 2026-11-04. What | search_hotels |
| KEEP | hotel-search-104 | baseline-pass | I'm looking for a hotel in Seattle with a pool and free WiFi for under $150 per night, staying 2026- | search_hotels |
| KEEP | hotel-search-105 | baseline-pass | I need a hotel for a family of 5 in Cancun for 5 nights starting 2026-06-20. Could you provide optio |  |
| DROP | hotel-search-106 | baseline-pass | I'm planning a visit to Barcelona and need to stay there for a few nights. Can you find available ho |  |
| DROP | hotel-search-107 | baseline-pass | Can you search for accommodations in Rome for a family of four from 2026-11-01 to 2026-11-05? | search_hotels |
| KEEP | hotel-search-108 | baseline-fail | Please find rooms in Sydney from August 8 to August 12 for 3 people. I also want to know what parkin |  |
| DROP | hotel-search-109 | baseline-pass | I've got my eye on the Marriott Aspen for the holidays. Before I plan anything else, please confirm  | check_availability |
| DROP | hotel-search-110 | baseline-pass | I’m planning a trip to Tokyo. Could you search for available hotels from December 5 to December 10 f | search_hotels |
| DROP | hotel-search-111 | baseline-pass | I'm looking to stay in Seattle for a weekend in November 2026. What do you recommend? |  |

## Reviewer decisions

Calibration of the original five drafts (and a first batch of extras) came back
all baseline-pass, so extras were generated (`generate --count 3`, twice) to
restore a pass/fail mix before promoting. Exactly five rows are KEEP.

KEEP (promoted five):

- hotel-search-101: search with landmark-view preference, Rome (baseline-pass)
- hotel-search-103: star-rating constraint, business trip, Sydney (baseline-pass)
- hotel-search-104: budget + amenities with conditional fallback, Seattle (baseline-pass)
- hotel-search-105: llm_judge multi-intent family case, Cancun (baseline-pass)
- hotel-search-108: llm_judge search + parking-options follow-through, Sydney
  (baseline-fail — scored 0.08 this run, 0.5 in the previous single trial; the
  no-skill agent answers about parking without returning hotel options)

DROP reasons:

- hotel-search-102: weakest/most generic of the original five — plain
  city+guests+dates search with no distinguishing constraint, same surface as
  107/110, and its dates are underspecified (no year). Swapped out for the
  baseline-fail extra 108 to keep the promoted count at exactly five.
- hotel-search-106: extra; missing-info intent (ask for dates) duplicates 111
  and the baseline already handles it (baseline-pass).
- hotel-search-107: extra; generic family search, paraphrase of 102/110 shape.
- hotel-search-109: extra; reviewer-edited into a check_availability probe
  (Marriott Aspen) hoping for a baseline-fail, but the baseline passes it —
  no longer needed once 108 calibrated baseline-fail.
- hotel-search-110: extra; generic city+dates+guests search, nothing new.
- hotel-search-111: extra; missing-info case, baseline-pass, overlaps 106.

