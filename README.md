# pr-comment-list

A [Claude Code](https://claude.com/claude-code) skill that reviews a GitHub pull
request and hands back a **triage list** — one line per comment, tagged, anchored
to a verified line number, with a permalink.

It doesn't post or change anything on its own. You read the list, keep the
comments you agree with, and drop the rest.

## Why

Most review tooling either posts findings straight to the PR or filters them down
to look decisive. Neither is what you want when *you're* the reviewer and your
name goes on the comment. This produces a list you can scan in one pass and paste
from.

Three things it does that matter:

- **Verified line numbers.** A comment on the wrong line reads as careless, so
  the anchors are computed from the diff rather than estimated. `pr_line_map.py`
  does the hunk arithmetic — headers restart the count, removed lines advance
  only the old file, renames change the path mid-diff — and reports which lines
  GitHub will actually accept an inline comment on.
- **Reads the thread first.** It pulls existing reviews and inline comments
  before looking at the diff, so it won't hand you a point someone already made
  or a question the author already answered. Repeats get marked
  `(already raised by …)` so you can decide whether to nudge.
- **Stays in scope.** A real defect on a line the PR didn't touch is dropped.
  Adding two tests to a file doesn't turn the rest of that file into a cleanup
  audit. The exception is when the diff makes an untouched line *newly* wrong —
  that gets flagged as `risk` with the causal link spelled out.

## Install

As a plugin:

```
/plugin marketplace add adink829/pr-comment-list
/plugin install pr-comment-list
```

Or drop the skill in by hand:

```bash
git clone https://github.com/adink829/pr-comment-list.git
ln -s "$PWD/pr-comment-list/skills/pr-comment-list" ~/.claude/skills/pr-comment-list
```

### Update

If you installed as a plugin, refresh the marketplace and then the plugin:

```
/plugin marketplace update adink829
/plugin update pr-comment-list@adink829
```

Then run `/reload-plugins` or restart the session. Updates are only detected when
the version in `.claude-plugin/plugin.json` changes.

If you installed by hand, pull the latest changes in your clone. The symlink
picks them up automatically:

```bash
cd pr-comment-list && git pull
```

## Requirements

- [`gh`](https://cli.github.com), authenticated (`gh auth status`)
- Python 3 (standard library only)
- A local checkout of the repo the PR targets

## Use

Paste a PR URL, or give a number or branch name:

```
https://github.com/owner/repo/pull/1234
review PR 1234
what should I comment on in my feature-branch PR?
```

It also handles re-reviews — "were my comments addressed?", "check if they fixed
it" — comparing the current head against the SHA you last looked at, from the file
diff rather than the commit list (which is useless after a rebase).

## Output

```markdown
# PR 1234 — Add segment filtering to the table

https://github.com/owner/repo/pull/1234

4 comments across 2 of 9 files. 1 bug, 1 risk, 1 question, 1 nit. 1 already raised.

## src/components/SearchBar.tsx

- **1 · L55** `bug` — Drops `width: '100%'`. Two other files use SearchBar, their layout may shift. [link](…)
- **2 · L59** `nit` — `textInputSize ?? 'small'` could be a default parameter. [link](…)

## src/components/DataTable.tsx

- **3 · L12-L20** `question` — Removed the 82px cell height. Rows may jump while loading. Intended? [link](…)

_Reviewed with nothing to flag: src/hooks/useFilters.ts, src/utils/paginate.ts, …_
```

### Acting on comments by number

Every comment gets a number, counting 1 to N across the whole list rather than
per file. Use the numbers to tell Claude what to do next, without copying or
retyping any comments:

```
post comments 1, 3, and 6
make the changes suggested by comments 2, 4, and 5
expand comment 3 into a full paragraph
```

Nothing is posted or changed until you ask.

### Tags

| Tag | Means |
| --- | --- |
| `bug` | Will behave wrong. Says what breaks. |
| `risk` | Might break something outside this PR — usually another caller of changed shared code. |
| `question` | Looks deliberate, but only the author knows the consequence. |
| `nit` | Style, naming, magic numbers. Safe to ignore. |

## Scripts

`skills/pr-comment-list/scripts/pr_line_map.py` is usable on its own:

```bash
# human-readable: files in diff order, every added line with its new-file number
python3 pr_line_map.py 1234 --repo-dir ~/code/myrepo

# or as JSON, to filter with jq
python3 pr_line_map.py https://github.com/owner/repo/pull/1234 --json
```

## License

Copyright (C) 2026 Alicia Dinkel

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version. See [LICENSE](LICENSE) for the full text.
