---
description: Find friends' birthdays from Instagram and Facebook, optionally add to Google Calendar
argument-hint: [--group close-friends|followers|following] [--sources facebook,stories,posts]
---

# /birthdays

Run the birthday-finder loop: figure out whose birthdays the user wants,
mine Facebook / Instagram stories / Instagram post captions, report
candidates with confidence and evidence, and — only on explicit approval —
add them to Google Calendar as yearly all-day events.

## Steps

1. Parse flags: `--group` (default `close-friends`), `--sources`
   (default all three: `facebook,stories,posts`). Plain-language requests
   work too — map them to the same options.
2. Read `skills/birthday-finder/SKILL.md` and follow it exactly.
3. Resolve the people list first (Close Friends / followers / following),
   and confirm the count with the user if it's ambiguous.
4. Run the sources the user asked for. The story-archive scan is slow
   (30–60 min for ~2k stories) — run it in the background and say so.
5. Present candidates grouped by confidence with evidence. Never present
   a guessed date as certain.
6. Only on explicit approval, add to Google Calendar: all-day, yearly
   recurring (`RRULE:FREQ=YEARLY`), transparent (shows as free).
7. Report what was added and what was skipped, and why.
