#!/usr/bin/env python3
"""Map a GitHub PR's diff to new-file line numbers.

Anchoring a review comment to the wrong line is worse than not commenting, and
the arithmetic is easy to get wrong by hand: every hunk header restarts the
count, removed lines advance the old file but not the new one, and renames
change the path mid-diff. This does that bookkeeping once so the reviewer can
spend its attention on the code instead.

Output per file: the files in diff order, the new-file line number of every
added line with its content, and each hunk's new-file range. GitHub only
accepts an inline comment on a line inside a hunk, so the ranges tell you what
is anchorable.

Usage:
    python pr_line_map.py <pr-number-or-url> [--repo-dir DIR]
    python pr_line_map.py <pr-number-or-url> --json
"""

import argparse
import json
import re
import subprocess
import sys

HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def run(cmd, cwd=None):
    result = subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        sys.exit(
            f"Command failed: {' '.join(cmd)}\n{result.stderr.strip()}"
        )
    return result.stdout


def parse_pr_ref(ref):
    """Accept a PR number, or a full github.com PR URL."""
    ref = ref.strip()
    if ref.isdigit():
        return ref, None
    match = re.search(r"github\.com/([^/]+/[^/]+)/pull/(\d+)", ref)
    if match:
        return match.group(2), match.group(1)
    sys.exit(f"Could not read a PR number from: {ref}")


def pr_metadata(pr_number, repo, cwd):
    cmd = [
        "gh", "pr", "view", pr_number,
        "--json", "number,title,url,headRefOid,headRefName,baseRefName,state,isDraft",
    ]
    if repo:
        cmd += ["--repo", repo]
    data = json.loads(run(cmd, cwd=cwd))
    # The permalink repo is the base repo the PR targets, which is what the
    # PR url points at -- not the head repo, which differs for forks.
    match = re.search(r"github\.com/([^/]+/[^/]+)/pull/", data["url"])
    data["nameWithOwner"] = match.group(1) if match else (repo or "")
    return data


def parse_diff(diff_text):
    """Walk a unified diff, tracking new-file line numbers."""
    files = []
    current = None
    new_line = None

    for raw in diff_text.split("\n"):
        if raw.startswith("diff --git "):
            # "diff --git a/old b/new" -- take the b/ side so renames land on
            # the path the comment will actually be posted against.
            match = re.match(r"^diff --git a/(.*) b/(.*)$", raw)
            current = {
                "path": match.group(2) if match else raw,
                "old_path": match.group(1) if match else None,
                "added": [],
                "hunks": [],
                "binary": False,
                "deleted": False,
            }
            files.append(current)
            new_line = None
            continue

        if current is None:
            continue

        if raw.startswith("Binary files "):
            current["binary"] = True
            continue
        if raw.startswith("+++ /dev/null"):
            current["deleted"] = True
            continue
        if raw.startswith(("--- ", "+++ ", "index ", "old mode ", "new mode ",
                           "new file mode ", "deleted file mode ",
                           "similarity index ", "rename from ", "rename to ",
                           "copy from ", "copy to ")):
            continue

        hunk = HUNK_RE.match(raw)
        if hunk:
            new_line = int(hunk.group(3))
            length = int(hunk.group(4)) if hunk.group(4) else 1
            current["hunks"].append(
                {"start": new_line, "end": new_line + max(length - 1, 0)}
            )
            continue

        if new_line is None:
            continue

        if raw.startswith("\\"):  # "\ No newline at end of file"
            continue
        if raw.startswith("+"):
            current["added"].append({"line": new_line, "text": raw[1:]})
            new_line += 1
        elif raw.startswith("-"):
            pass  # advances the old file only
        else:
            # Context line. A fully empty string is a context line whose
            # content was empty and whose leading space got stripped.
            new_line += 1

    return files


def fmt_ranges(hunks):
    return ", ".join(f"{h['start']}-{h['end']}" for h in hunks) or "(none)"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pr", help="PR number or github.com PR URL")
    parser.add_argument("--repo-dir", default=".", help="local checkout to run gh in")
    parser.add_argument("--repo", help="owner/name, if not inferable")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    args = parser.parse_args()

    pr_number, repo_from_url = parse_pr_ref(args.pr)
    repo = args.repo or repo_from_url

    meta = pr_metadata(pr_number, repo, args.repo_dir)

    diff_cmd = ["gh", "pr", "diff", pr_number]
    if repo:
        diff_cmd += ["--repo", repo]
    files = parse_diff(run(diff_cmd, cwd=args.repo_dir))

    sha = meta["headRefOid"]
    slug = meta["nameWithOwner"]
    permalink = f"https://github.com/{slug}/blob/{sha}"

    if args.json:
        print(json.dumps({"pr": meta, "permalink_prefix": permalink,
                          "files": files}, indent=2))
        return

    print(f"PR {meta['number']}: {meta['title']}")
    print(f"URL:        {meta['url']}")
    print(f"State:      {meta['state']}{' (DRAFT)' if meta['isDraft'] else ''}")
    print(f"Base:       {meta['baseRefName']}")
    print(f"Head SHA:   {sha}")
    print(f"Permalink:  {permalink}/<path>#L<start>-L<end>")
    print(f"Files:      {len(files)} (listed in diff order below)")
    print()

    for index, f in enumerate(files, 1):
        print("=" * 70)
        print(f"[{index}/{len(files)}] {f['path']}")
        if f["old_path"] and f["old_path"] != f["path"]:
            print(f"  renamed from: {f['old_path']}")
        if f["binary"]:
            print("  (binary file -- no line map)")
            print()
            continue
        if f["deleted"]:
            print("  (file deleted -- nothing to anchor in the new file)")
            print()
            continue
        print(f"  commentable new-file ranges: {fmt_ranges(f['hunks'])}")
        print(f"  added lines: {len(f['added'])}")
        print()
        for entry in f["added"]:
            print(f"  {entry['line']:>6} + {entry['text']}")
        print()


if __name__ == "__main__":
    main()
