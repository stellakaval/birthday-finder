#!/usr/bin/env python3
"""Scan a user's Instagram story archive for birthday shoutout posts.

Enumerates the archive via `instagram-cli own-stories-archive`, downloads
thumbnails, and OCRs them for birthday keywords. Writes candidates as JSON:
[{id, created_at, media_type, ocr}].

Name matching and confidence scoring are the agent's job -- this script
only gathers evidence.

Usage:
    pip install -r requirements.txt
    python3 scan_stories.py --account-id <fbid> --out state/candidates.json

Runs for a long time on big archives (~30-60 min for ~2k stories).
Checkpointing means a killed run resumes where it left off.
"""

import argparse
import json
import os
import subprocess
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from multiprocessing import Pool

DEFAULT_KEYWORDS = ["birthday", "bday", "hbd", "happy b", "turning ",
                    "hbday", "b-day"]


def sh(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[:200] or "command failed: " + " ".join(cmd))
    return r.stdout


def enumerate_archive(account_id, max_pages=0):
    """Page through own-stories-archive; return list of story dicts."""
    items, max_id, pages = [], None, 0
    while True:
        cmd = ["instagram-cli", "own-stories-archive",
               "--account-id", account_id]
        if max_id:
            cmd += ["--max-id", max_id]
        try:
            data = json.loads(sh(cmd))
        except Exception as e:
            print(f"archive page failed: {e}", flush=True)
            break
        batch = data.get("items") or data.get("stories") or []
        if not batch:
            break
        for it in batch:
            media = it.get("media") or it
            items.append({
                "id": str(it.get("id") or media.get("id")),
                "created_at": it.get("created_at") or media.get("created_at"),
                "media_type": it.get("media_type") or media.get("media_type"),
                "image_url": it.get("image_url") or media.get("image_url"),
            })
        pages += 1
        max_id = data.get("next_max_id")
        if not max_id or (max_pages and pages >= max_pages):
            break
        print(f"archive page {pages}: {len(items)} stories", flush=True)
    return items


def download(args):
    it, thumbdir = args
    sid, url = it["id"], it.get("image_url")
    if not url:
        return {"id": sid, "error": "no image_url"}
    p = os.path.join(thumbdir, f"{sid}.jpg")
    if os.path.exists(p):
        return {"id": sid, "path": p, "created_at": it["created_at"],
                "media_type": it.get("media_type")}
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
        with open(p, "wb") as f:
            f.write(data)
        return {"id": sid, "path": p, "created_at": it["created_at"],
                "media_type": it.get("media_type")}
    except Exception as e:
        return {"id": sid, "error": f"download: {e}"[:120]}


_engine = None


def init_worker():
    global _engine
    from rapidocr_onnxruntime import RapidOCR
    _engine = RapidOCR()


def ocr_file(path):
    try:
        res = _engine(path)
        texts = [t[1] for t in res[0]] if res and res[0] else []
        return " ".join(texts)
    except Exception as e:
        return "ERROR: " + str(e)[:120]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--account-id", required=True)
    ap.add_argument("--out", required=True, help="candidates JSON output path")
    ap.add_argument("--workdir", default="state/story_thumbs",
                    help="thumbnail download dir (NOT /tmp -- can be 500MB+)")
    ap.add_argument("--max-pages", type=int, default=0,
                    help="limit archive pages (0 = all)")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--chunk-size", type=int, default=400)
    ap.add_argument("--keywords", default=",".join(DEFAULT_KEYWORDS))
    ap.add_argument("--resume", action="store_true",
                    help="resume from checkpoint instead of starting over")
    args = ap.parse_args()
    keywords = [k for k in args.keywords.split(",") if k]

    os.makedirs(args.workdir, exist_ok=True)
    ckpt = os.path.join(os.path.dirname(args.out) or ".", "scan_checkpoint.json")
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)

    items = enumerate_archive(args.account_id, args.max_pages)
    print(f"enumerated {len(items)} stories", flush=True)

    print("downloading thumbnails...", flush=True)
    jobs, dl_errors = [], []
    with ThreadPoolExecutor(max_workers=16) as ex:
        for res in ex.map(download, [(it, args.workdir) for it in items]):
            if "path" in res:
                jobs.append(res)
            else:
                dl_errors.append(res)
    print(f"downloaded {len(jobs)}/{len(items)}", flush=True)

    done_ids, matches, errors = set(), [], list(dl_errors)
    if args.resume and os.path.exists(ckpt):
        ck = json.load(open(ckpt))
        done_ids = set(ck.get("done", []))
        matches = ck.get("matches", [])
        errors += ck.get("errors", [])
    todo = [j for j in jobs if j["id"] not in done_ids]
    print(f"todo={len(todo)} already={len(done_ids)}", flush=True)

    total = len(jobs)
    for ci in range(0, len(todo), args.chunk_size):
        chunk = todo[ci:ci + args.chunk_size]
        pool = Pool(args.workers, initializer=init_worker)
        try:
            for j in chunk:
                text = pool.apply(ocr_file, (j["path"],))
                done_ids.add(j["id"])
                if text.startswith("ERROR:"):
                    errors.append({"id": j["id"], "error": text})
                elif any(k in text.lower() for k in keywords):
                    matches.append({"id": j["id"], "created_at": j["created_at"],
                                    "media_type": j.get("media_type"),
                                    "ocr": text[:800]})
                n = len(done_ids)
                if n % 100 == 0:
                    json.dump({"done": sorted(done_ids), "matches": matches,
                               "errors": errors}, open(ckpt, "w"))
                    print(f"progress {n}/{total} matches={len(matches)}", flush=True)
        finally:
            pool.close()
            pool.join()
        print(f"chunk done {len(done_ids)}/{total}", flush=True)

    json.dump(matches, open(args.out, "w"), indent=1)
    json.dump({"done": sorted(done_ids), "matches": matches, "errors": errors},
              open(ckpt, "w"))
    print(f"DONE candidates={len(matches)} errors={len(errors)} total={total}",
          flush=True)


if __name__ == "__main__":
    main()
