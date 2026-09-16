---
name: birthday-finder
description: Finds friends' birthdays by mining Facebook friend birthdays, the user's Instagram story archive (OCR for birthday shoutouts), and Instagram post captions, then optionally adds them to Google Calendar as yearly events. Use when someone asks to find, collect, or track birthdays for friends, family, close friends, followers, or any group of people — or asks "when is X's birthday".
---

# birthday-finder

Instagram doesn't expose anyone's birthday through its API — not even your
close friends'. Facebook has birthdays but only for friends who share them.
So this skill plays detective across three sources, scores what it finds,
and only touches your calendar when you say so.

Backed by `scripts/scan_stories.py`, which enumerates the story archive
and OCRs thumbnails for birthday text. Name matching, confidence scoring,
and the calendar decision are the agent's job — the script only gathers.

## The core loop

### 1. Resolve the people list

Ask (or infer from the request) whose birthdays to find:

- `close-friends` (default) — `instagram-cli close-friends-list --account-id <fbid>`
- `followers` / `following` — the corresponding `instagram-cli` commands
- named individuals — match against the above lists where possible

Keep each person's `username` and `full_name`. Confirm the count with the
user if the group is ambiguous ("your 119 close friends" — yes/no).

### 2. Source A — Facebook birthdays

Pull the user's Facebook friends with birthdays
(`facebook-cli`, friends list with birthday fields; a 365-day upcoming
window works well). Match to the people list:

- Normalize both sides: lowercase, strip everything that isn't `[a-z0-9]`.
- Exact normalized match first, then first+last-name fallback, then fuzzy
  (`difflib`, cutoff ~0.85) — and flag fuzzy matches as lower confidence.
- A Facebook friend with no visible birthdate is not a "no", it's an
  "unknown" — say so.

Facebook-sourced dates are **high confidence** (self-reported), but only
cover people who share them.

### 3. Source B — Instagram story archive (the big one)

Run `python3 scripts/scan_stories.py --account-id <fbid> --out
state/story_bday_candidates.json --workdir state/story_thumbs`.
It paginates `instagram-cli own-stories-archive`, downloads thumbnails,
and OCRs them for birthday keywords. **Run it in the background** — a
~2,000-story archive takes 30–60 minutes. Tell the user that upfront and
report back when it finishes.

For each candidate the script returns the story's `id`, `created_at`
(unix), `media_type`, and the OCR'd text. Your job:

- Extract who the post is for: `@mentions` first (normalize and match to
  the people list as in step 2), then first names, then display names in
  the text.
- The birthday = the story's **post date** (month/day). Year doesn't matter.
- **Confidence rubric:**
  - *High* — same person, same month/day, 2+ different years; or a clear
    `@mention` plus an unambiguous "happy birthday" with a full name.
  - *Medium* — single tagged post, or first-name-only mention that matches
    exactly one person on the list.
  - *Low* — ambiguous text (a sign in the background, "national siblings
    day", a pet name with no tag, first name matching multiple people).
    Report these separately or not at all — your call, but never silently
    promote them.
- Discard obvious noise: background signage, "birthday" in an unrelated
  sentence, someone else's reposted content where the birthday person is
  unclear.

### 4. Source C — Instagram post captions

Cheaper than stories and often just as good: pull recent feed posts
(`instagram-cli posts`) and grep captions for birthday keywords +
`@mentions`. Same matching and confidence rules as Source B. Go back as
far as is reasonable (a year or two of posts is usually enough signal).

### 5. Present the report

Group by confidence. Every entry carries its evidence:

- **New birthdays (high confidence)** — name, month/day, evidence
  ("birthday story posted Aug 11 in 2023 and 2024").
- **Likely (medium)** — same, noting it's a single post.
- **Uncertain (low)** — flagged clearly, e.g. "Oct 3? — one 2018 story,
  also mentions 'scouts'".
- **Confirmed** — dates from one source backed up by another.
- **Not found** — who had no discoverable birthday (not proof they lack
  one everywhere, just that these sources came up empty).

Never present a guessed date as certain. Never inflate: "found 12 of 119"
is the honest headline, not "birthdays: solved".

### 6. Calendar — only on explicit approval

The user must say so (a tap on an approval widget counts). Then, for each
approved date, create on their primary Google Calendar via the
`google_calendar` skill (`hatch_gws_cli calendar events insert`):

```json
{
  "summary": "<Name>'s Birthday",
  "description": "<source/evidence, e.g. 'Birthday shoutout in IG stories (Aug 11, 2023 & 2024)'>",
  "start": {"date": "2026-08-11"},
  "end": {"date": "2026-08-12"},
  "recurrence": ["RRULE:FREQ=YEARLY"],
  "transparency": "transparent"
}
```

All-day, yearly, transparent (shows as free — birthdays aren't meetings).
Put the evidence and confidence in the description so future-them knows
where the date came from. Report what was added and what was skipped.

## Hard-won notes (read before running Source B)

- `instagram-cli media-understanding` returns nulls for story media IDs —
  don't bother; OCR on thumbnails is the working path.
- Don't assume `tesseract` exists. `rapidocr-onnxruntime` (pip,
  `scripts/requirements.txt`) works headless and reads story text well.
  Test it on one real thumbnail before launching the full scan.
- `/tmp` is often a small tmpfs — a full archive's thumbnails can be
  500MB+. Download into the plugin's `state/` dir (gitignored) and clean
  up when done.
- Keep OCR worker processes persistent (one model load each, reused),
  process in chunks, and checkpoint every ~100 stories — a dead run
  resumes instead of restarting.
- Account for API politeness: threaded downloads are fine, but don't
  hammer; 12–16 download threads is plenty.
- Story dates are in unix seconds; convert to the user's local timezone
  when presenting month/day.
- Video stories have thumbnails too — include them (the cover frame often
  has the birthday text).

## Honest limitations

- Post date ≈ birthday, but people post late/early. ±1–2 days happens.
- Textless birthday posts (photo + GIF sticker, no words) are invisible
  to this method.
- OCR misreads handles (`@sophieechung` → `@SOPHIEECHUNG` is fine;
  `tiffpham` → `gtiffpham` needs fuzzy matching). Always eyeball matches.
- This finds birthdays people *posted about*. Quiet friendships leave no
  trace — that's a coverage gap, not a failure.
- Calendar writes are the only irreversible-ish step here, and they need
  explicit approval every time. No standing "just add them" — ask per run.
