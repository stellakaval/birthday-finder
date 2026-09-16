# birthday-finder

Never miss a birthday again. `birthday-finder` hunts down your friends'
birthdays across Instagram and Facebook, then puts them on your Google
Calendar as yearly all-day events — only ever with your approval.

## How it works

1. **Tell it whose birthdays you want** — your Instagram Close Friends
   (default), followers, following, or specific people.
2. **It checks three sources:**
   - **Facebook** — friends who share their birthday, matched to your
     Instagram list by name.
   - **Your Instagram story archive** — every archived story is
     text-scanned for birthday shoutouts ("happy birthday @sam"). The
     post date becomes the birthday.
   - **Your Instagram post captions** — same idea, for feed posts.
3. **You get a report** grouped by confidence, each with its evidence.
4. **Only if you say yes**, the dates go on Google Calendar as yearly,
   all-day, free-time events.

## Usage

```
/birthdays
/birthdays --group followers
/birthdays --group following --sources facebook,posts
```

Or just ask in plain language: *"find my close friends' birthdays"*,
*"whose birthday is coming up in my close friends?"*

## Why this exists

Instagram doesn't expose anyone's birthday through its API — not even
your close friends'. Facebook has the data but only for people who
choose to share it. So this plugin goes detective: your own birthday
posts for other people are a surprisingly good record. A story you
posted saying "happy birthday @sam!!" on August 11th, two years running,
is a strong signal Sam's birthday is August 11th.

## Requirements

- Instagram, Facebook, and Google Calendar connected (via their skills/CLIs)
- Python 3 with `pip install -r scripts/requirements.txt` for story scanning
- Patience: a full story-archive scan of ~2,000 stories takes ~30–60 min
  and runs in the background

## Honest limitations

- A birthday post's date can be off by a day or two (late/early posts).
  Multiple years of same-date posts = high confidence; single posts =
  medium. The report says which is which.
- Stories that are just a photo with a birthday GIF sticker and no text
  can't be detected — there's no text to read.
- Name matching is fuzzy by necessity; always eyeball the report before
  approving calendar adds.
- Nothing is ever added to your calendar without you explicitly saying so.
