---
description: Find friends' birthdays across Instagram, Facebook, Messenger, and WhatsApp; optionally add to Google Calendar
argument-hint: [--group close-friends|followers|following] [--sources facebook,ig-stories,ig-posts,fb-posts,fb-stories,messenger,ig-dms,whatsapp]
---

# /birthdays

Run the birthday-finder loop: figure out whose birthdays the user wants,
mine all seven sources **in parallel** (Facebook birthdays/posts/stories,
Instagram story archive/posts/DMs, Messenger, WhatsApp), report
candidates with confidence and evidence, and — only on explicit approval —
add them to Google Calendar as yearly all-day events.

## Steps

1. Parse flags: `--group` (default `close-friends`), `--sources`
   (default all seven). Plain-language requests work too — map them to
   the same options.
2. Read `skills/birthday-finder/SKILL.md` and follow it exactly —
   especially the parallel execution pattern in step 2.
3. Resolve the people list first (Close Friends / followers / following),
   and confirm the count with the user if it's ambiguous.
4. Launch one worker per enabled source concurrently (subagents, or
   parallel background calls). The story-archive scan is slow (30–60 min
   for ~2k stories) — start it first, in the background, and say so.
5. Merge results as they arrive; wait for all enabled sources before the
   final report. Present candidates grouped by confidence with evidence.
   Never present a guessed date as certain.
6. Only on explicit approval, add to Google Calendar: all-day, yearly
   recurring (`RRULE:FREQ=YEARLY`), transparent (shows as free).
7. Report what was added and what was skipped, and why.
