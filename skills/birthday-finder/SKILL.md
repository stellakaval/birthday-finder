---
name: birthday-finder
description: Finds friends' birthdays by mining Facebook (friend birthdays, posts, stories), Instagram (story archive OCR, post captions, DMs), Messenger, and WhatsApp, then optionally adds them to Google Calendar as yearly events. Use when someone asks to find, collect, or track birthdays for friends, family, close friends, followers, or any group of people — or asks "when is X's birthday".
---

# birthday-finder

Instagram doesn't expose anyone's birthday through its API — not even your
close friends'. Facebook has birthdays but only for friends who share them.
So this skill plays detective across **seven sources**, scores what it
finds, and only touches your calendar when you say so.

Backed by `scripts/scan_stories.py`, which enumerates the Instagram story
archive and OCRs thumbnails for birthday text. Name matching, confidence
scoring, and the calendar decision are the agent's job — the script only
gathers.

## The core loop

### 1. Resolve the people list

Ask (or infer from the request) whose birthdays to find:

- `close-friends` (default) — `instagram-cli close-friends-list --account-id <fbid>`
- `followers` / `following` — the corresponding `instagram-cli` commands
- named individuals — match against the above lists where possible

Keep each person's `username` and `full_name`. Confirm the count with the
user if the group is ambiguous ("your 119 close friends" — yes/no).

### 2. Gather — run every source in parallel

Each source below is independent. **Run them concurrently**: spawn one
subagent per source, or fire the CLI batches as parallel background calls.
Do not run them one-by-one — the wall-clock difference is large (the
story-archive scan alone is 30–60 min). Merge results in step 3 as each
source returns.

Which sources to run: all by default; `--sources` narrows it
(`facebook,ig-stories,ig-posts,fb-posts,fb-stories,messenger,ig-dms,whatsapp`).
Skip any platform whose skill isn't connected and say so.

- **A. Facebook birthdays** (`facebook_cli`): pull friends with birthdays
  (a 365-day upcoming window works well). Normalize names both sides
  (lowercase, strip non-`[a-z0-9]`) and match: exact first, then
  first+last, then fuzzy (`difflib`, cutoff ~0.85, flagged lower
  confidence). A friend with no visible birthdate is "unknown", not "no".
  Self-reported dates = **high confidence**, but only cover sharers.

- **B. Instagram story archive** (slow — background it): run
  `python3 scripts/scan_stories.py --account-id <fbid> --out
  state/story_bday_candidates.json --workdir state/story_thumbs`.
  Returns `[{id, created_at, media_type, ocr}]`. Extract the birthday
  person from `@mentions` first, then names. Birthday = post date
  (month/day). Tell the user this one takes a while and report back when
  it lands.

- **C. Instagram post captions** (`instagram`): pull feed posts
  (`instagram-cli posts`, paginated — it returns the full visible history,
  hundreds of posts) and grep captions for birthday keywords +
  `@mentions`. Same matching as B, much faster. Note: neither Instagram
  nor Facebook exposes a *post* archive API (only IG's story archive
  exists) — deep pagination over posts/timeline is the complete
  reachable history.

- **D. Facebook posts** (`facebook_cli`): resolve your id first
  (`facebook-cli me` → `fb_user_id`; `--profile-id me` 404s), then
  `timeline fetch --profile-id <id>` and page back — the list view has no
  post text, so run `post read --post-id` on candidates. `social.search`
  is a secondary angle for own posts (hit-or-miss on history). Tagged
  friends and mentioned names map back to the people list.

- **E. Facebook stories** (`facebook_cli`): `story feed` shows the
  *current* 24h tray — there is no story archive API, so this source only
  sees what's live right now. Check the response for text overlays first;
  if absent, OCR thumbnails the same way as Source B. Best used as a
  recurring check rather than a one-shot.

- **F. DMs — Messenger + Instagram** (`messenger`, `instagram_messages`):
  keyword-search both for birthday variants
  (`hatch_messenger_cli search "happy birthday"`,
  `instagram-messages-cli keyword-search --query-text "happy birthday"`).
  Message date = birthday. In 1:1 chats the other participant is the
  birthday person; in group chats, read the message to see who it's
  addressed to before attributing. Date the message, not the reply. The
  IG response carries `thread_name` for attribution; `timestamp_ms` is a
  string.

- **G. WhatsApp** (`whatsapp`): `hatch_wai_cli` message search for
  birthday variants across chats. Chat name → person; in groups, confirm
  who the wish is for. Narrow keyword searches only — no bulk history
  export (the skill refuses it, and rightly so). Note: synced history may
  be incomplete, so absence here proves nothing.

### 3. Merge, match, score

Combine all sources per person. Dedupe: the same birthday from stories +
a DM is one finding with two evidences, not two findings.

**Confidence rubric:**
- *High* — same person, same month/day, 2+ sources or 2+ years; or a
  self-reported Facebook birthdate.
- *Medium* — single tagged post / single 1:1 DM / single WhatsApp wish.
- *Low* — ambiguous text (background signage, first name matching
  multiple people, group-chat wish with unclear addressee, "national
  sibling day" noise). Report separately, never silently promoted.

Discard obvious noise: signage in the background, "birthday" in an
unrelated sentence, reposted content where the birthday person is
unclear.

### 4. Present the report

Group by confidence. Every entry carries its evidence:

- **New birthdays (high confidence)** — name, month/day, evidence
  ("birthday story Aug 11 in 2023 and 2024; WhatsApp wish Aug 11").
- **Likely (medium)** — same, noting it's a single source.
- **Uncertain (low)** — flagged clearly ("Oct 3? — one 2018 story, also
  mentions 'scouts'").
- **Confirmed** — dates backed by 2+ sources.
- **Not found** — no discoverable birthday in these sources (coverage
  gap, not proof of absence).

Never present a guessed date as certain. "Found 12 of 119" is the honest
headline, not "birthdays: solved".

### 5. Calendar — only on explicit approval

The user must say so (a tap on an approval widget counts). Then, for each
approved date, create on their primary Google Calendar via the
`google_calendar` skill (`hatch_gws_cli calendar events insert`):

```json
{
  "summary": "<Name>'s Birthday",
  "description": "<source/evidence, e.g. 'Birthday shoutout in IG stories (Aug 11, 2023 & 2024); confirmed by WhatsApp message'>",
  "start": {"date": "2026-08-11"},
  "end": {"date": "2026-08-12"},
  "recurrence": ["RRULE:FREQ=YEARLY"],
  "transparency": "transparent"
}
```

All-day, yearly, transparent (shows as free — birthdays aren't meetings).
Evidence and confidence go in the description. Report what was added and
what was skipped.

## Parallel execution pattern

Phase 1 (gather) is embarrassingly parallel — treat it that way:

1. Resolve the people list first (everything else depends on it).
2. Launch one worker per enabled source at the same time: subagents are
   cleanest (each inherits the transcript and returns evidence JSON), or
   parallel background `exec` calls for the quick CLI sources.
3. The story-archive scan is the long pole — start it first, in the
   background, and say so.
4. Merge in step 3 as results arrive; don't block quick sources on slow
   ones for the *interim* report, but do wait for all enabled sources
   before the final calendar proposal.

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
- Story dates are unix seconds; convert to the user's local timezone for
  month/day. Video stories have thumbnails too — include them.
- For DMs/WhatsApp: search, don't scroll. Keyword searches
  ("happy birthday", "hbd", "happy bday", "happy belated birthday") over
  a date range beat reading threads. In group chats always verify the
  addressee.

## Honest limitations

- Post/message date ≈ birthday, but people post late/early. ±1–2 days
  happens; "belated" wishes date the *wish*, not the birthday — read the
  text.
- Textless birthday posts (photo + GIF sticker, no words) are invisible
  to this method.
- Facebook has no story archive API — Source E only sees the live tray.
- WhatsApp history may be incomplete after linking; Messenger/IG search
  won't see vanished messages.
- OCR misreads handles; fuzzy-match and eyeball everything.
- This finds birthdays people *posted or messaged about*. Quiet
  friendships leave no trace — a coverage gap, not a failure.
- Calendar writes are the only irreversible-ish step and need explicit
  approval every run. No standing "just add them" — ask per run.
