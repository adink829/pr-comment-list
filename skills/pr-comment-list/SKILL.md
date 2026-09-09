---
name: pr-comment-list
description: Review a GitHub pull request and return a triage list — each file with findings, in diff order, with one-line tagged comments anchored to verified line numbers and permalinks. Reads the existing PR comments first so it never repeats a point already made. Read-only; it never posts. Use this whenever the user pastes a github.com pull request URL, gives a PR number or branch and asks for a review, or asks any variant of "what should I comment on", "what lines should I comment on", "review this PR", "review this diff", or "give me comments for this PR" — even if they don't say the word "review". Also use it to re-review: "were my comments addressed", "check if they fixed it", "re-review this PR", or any ask about what changed since a previous look. Prefer this over other review skills when the user wants to decide for themselves which comments to keep rather than have findings posted or filtered for them.
---

# PR comment list

Produce a list the user can triage in one pass: files in the order GitHub shows
them, and under each file one bullet per comment, each tagged and anchored to a
real line number with a link.

The user reads this to decide what to say on the PR. They keep some comments and
discard others. That shapes everything below:

- **The line number has to be right.** A comment pointing at the wrong line is
  worse than no comment, because they'll paste it and look careless. Verify
  every number against the head commit. Never estimate.
- **Include the small stuff, within scope.** They asked for nits too, so don't
  pre-filter to look decisive — a discarded nit costs them two seconds, a missed
  bug costs a lot more. "Within scope" is the limit: nits about lines this PR
  wrote, not about old code the PR happened to sit next to. See the scope rule in
  Step 4.
- **One line per comment.** They're scanning, not reading. If a point needs
  three sentences to land, it's usually two points, or you don't understand it
  yet.
- **Plain English.** Short words. Say what breaks and what to check. Skip the
  vocabulary that makes reviews sound authoritative — "this violates the
  single-responsibility principle" tells them nothing they can act on.

## Ground rules

**Read only.** Never post a comment, never push, never edit a file, never
approve. You are producing text for the user to use. Nothing you do touches the
PR.

**Don't ask permission** to fetch the PR, run `gh`, read files, or search the
repo. That's assumed. Just go. The only reason to stop and ask is if you can't
identify which PR they mean.

**Never use `cd`.** Use `git -C <abs-repo-path> <subcommand>` and `gh --repo
<owner>/<name>`. A `cd` inside a compound command triggers a permission prompt
even when the git read after it is pre-approved, so `cd <repo> && git show ...`
interrupts the user for no reason while `git -C <repo> show ...` runs silently.

## Step 1 — Find the PR

Accept a URL, a number, or a branch name. If they gave a branch:

```bash
gh pr list --head <branch> --state all --json number,title,url,state,isDraft
```

If the PR lives in a repo other than the current directory, pass `--repo
owner/name` to every `gh` call.

## Step 2 — Read what's already been said

Do this **before** reviewing the diff, not after. Repeating a point someone
already made is the fastest way to make the user look like they didn't read the
thread, and a question the author already answered in a comment is worse than no
question.

Three separate surfaces, and the inline one needs the API — `gh pr view` does not
return it:

```bash
gh pr view <n> --json reviews,comments,author,headRefOid
gh api repos/<owner>/<repo>/pulls/<n>/comments --jq '.[] | {path, line, user: .user.login, body}'
```

What to do with each:

- **The user's own prior comments are the highest-signal input you'll get.** They
  tell you what this reviewer actually cares about on this PR. If they raised a
  concern and it's still live, carry it forward and say so. If they already
  approved a choice, don't relitigate it.
- **A point already raised by anyone** — don't restate it as if it were yours. If
  it's genuinely unaddressed, keep the bullet but append
  `(already raised by <who> — <link to the comment>)` so the user can decide
  whether to nudge rather than repeat.
- **Answered questions are closed.** If the author explained a choice in a reply,
  drop the question. If their explanation doesn't hold up, that's a different and
  much better comment — say what's wrong with the reasoning.
- **Bot reviews are low signal.** `chatgpt-codex-connector`, dependabot and
  friends. "Didn't find any major issues" is not evidence of anything. Read them
  but don't weight them, and never cite one as support.

### If the head moved since a prior review

Compare what you're looking at now against the SHA that was reviewed:

```bash
git -C <repo> diff <old-head-sha>..<new-head-sha> -- <the files the comments touched>
```

**Do not trust the commit list.** After a rebase every commit in the PR gets a
new SHA, so `git log <old>..<new>` reports all of them as new work and their
titles will read like fixes that already existed when you last looked. A commit
titled "Await the user interactions" may have awaited three calls in a test it
was adding and touched nothing else. The file diff is the only reliable evidence
of what actually changed; check the current state of the file for anything you
claim was or wasn't fixed.

When re-reviewing, lead with a short verdict per prior comment — addressed, still
open, or moot — before the new findings. That's usually the whole answer the user
wants.

## Step 3 — Build the line map

```bash
python <skill-dir>/scripts/pr_line_map.py <pr-number-or-url> --repo-dir <checkout>
```

This prints the head SHA, the permalink prefix, the files **in diff order**, and
for each file every added line with its new-file line number plus the hunk
ranges GitHub will accept a comment on. Use its file order as your output order
— it's the diff's own order, which is what the user sees on github.com.

To pull line numbers for just the files you care about, add `--json` and filter
with `jq` — not an inline `python3 -c` script. `jq` is pre-approved and runs
without interrupting the user; ad-hoc `python3 -c` cannot be allowlisted safely
(it is arbitrary code) so every call prompts. Example:

```bash
python3 <skill-dir>/scripts/pr_line_map.py <pr> --repo-dir <checkout> --json \
  | jq -r '.files[] | select(.path | test("SegmentsTable")) as $f
           | "### \($f.path)", ($f.added[] | "  \(.line) | \(.text)")'
```

The script exists because this arithmetic is fiddly (hunk headers restart the
count, removed lines advance only the old file, renames change the path
mid-diff) and getting it wrong silently produces confident, wrong anchors.

If it fails for any reason, fall back to reading `gh pr diff <n>` and counting
hunk headers yourself — but then spot-check two or three anchors against
`git -C <repo> show <sha>:<path>` before writing them down.

## Step 4 — Review each file

Read the diff. Pull in surrounding context with `git -C <repo> show <sha>:<path>` when a
change's effect isn't visible in the hunk alone.

Things that reliably matter, roughly in order of how often they turn up
something real:

- **Changed shared code — who else calls it?** If the PR edits an exported
  component, hook, or helper, grep for other callers. A layout or signature
  change that's correct for the page in the PR may quietly break two others.
  This is the single highest-yield check.
- **Tests that don't test anything.** Does the assertion still pass if the code
  under test is deleted? Does it re-prove a mock's own logic rather than the
  real behavior? Is it a hardcoded count that passes without the code running?
  Say specifically what the test fails to catch.
- **Removed guards, constants, or boundaries.** If the diff deletes an explicit
  height, a null check, a debounce, or an error boundary, ask why it was there.
  `git log -S'<the removed token>' -- <path>` often finds the bug it was fixing.
- **Deleted tests and stories.** What coverage went away, and is it covered
  elsewhere now?
- **Off-by-one and empty-set math.** Page clamping, slicing, counts, division
  where the denominator could be zero.
- **Async gaps.** Un-awaited calls, effects that can fire twice, state written
  during render.
- **Nits worth a bullet.** Magic numbers, naming that fights the codebase,
  duplicated logic, a comment that the change made untrue.

Check the repo's `CLAUDE.md` / `AGENTS.md` if present. Flag a rule violation
only when the file actually states the rule — quote it in the bullet.

Skip things CI already catches: formatting, type errors, lint, import order.
The user doesn't need you for those.

### Scope: only lines this PR touched

**A defect on a line the PR did not add or change is out of scope, even when it
is real.** Check it against the added-lines list from Step 3 before writing a
bullet. If the line isn't there, drop it.

This matters most in test files, and the trap is specific: a PR adds two tests to
a file, you read the whole file, and you notice eight un-awaited `userEvent`
calls, a brittle `parentElement` chain, and a magic row count — none of which
this PR wrote. Reporting those turns a focused review into a cleanup audit of
someone else's old code. The author has to defend work they didn't do, and the
real findings get buried. **Adding a test to a file does not put the rest of the
file in scope.**

Same for source files: an existing `TODO`, a pre-existing null-check gap, a
duplicated helper that predates the branch. Not this PR's job.

**The one exception is when the diff makes an untouched line newly wrong.** That
isn't a pre-existing issue, it's this PR breaking something, and it's often the
most valuable thing you'll find. Examples:

- The PR flips feature flags on in a shared story default, so an existing test in
  another file now renders content it didn't before.
- The PR changes an exported component's props or layout, and an untouched caller
  gets a phantom column or a shifted layout.
- The PR changes a `requestId` format or an enum, and an untouched parser that
  reads it now silently returns zero.

Tag those `risk`, and **say what in the diff makes the old line wrong** — name the
changed line and the consequence. A bullet that just points at old code without
that causal link is the thing this section exists to stop.

When you drop something real for being out of scope and it seems worth knowing,
put it in a sentence after the file list — not as a bullet with a line anchor.
The user can decide whether it deserves its own cleanup ticket.

## Step 5 — Write the output

Use this shape exactly:

```markdown
# PR <number> — <title>

<link to the PR>

<N> comments across <M> of <T> files. <counts by tag>. <X already raised.>

## <path/as/shown/in/diff.ext>

- **L55** `bug` — Drops `width: '100%'`. Two other files use SearchBar, their layout may shift. [link](permalink)
- **L59** `nit` — `textInputSize ?? 'small'` could be a default parameter. [link](permalink)

## <path/to/another.ext>

- **L12-L20** `question` — Removed the 82px cell height. Rows may jump while loading. Intended? [link](permalink)

_Reviewed with nothing to flag: path/a.ts, path/b.tsx, path/c/index.ts_
```

Rules for the output:

- **Only files with comments get a heading**, in diff order. A heading with
  "Nothing to flag." under it is a line the user has to read to learn nothing —
  on a 17-file PR that's most of the page.
- **Close with one italic line naming the clean files**, so they still know you
  looked at all of them rather than quietly skipping some. Paths only, comma
  separated, no bullets. Drop the line entirely when every file has a comment.
- **The count line up front** tells them how big the job is before they start.
  Say `<M> of <T> files` so the gap between the two makes the clean count obvious.
- **Line numbers are new-file numbers** and must sit inside a hunk range from
  the script. The *finding* has to be about something the PR added or changed;
  the *anchor* may be a nearby context line inside the same hunk when that reads
  better — the `it(...)` declaration above a changed assertion, say.
- **A line outside every hunk is only reportable under the "newly wrong"
  exception** in Step 4. Then append `(not inline-commentable — needs a top-level
  comment)` so they don't hunt for a line GitHub won't let them annotate. If the
  line is merely pre-existing and imperfect, it doesn't go in the list at all —
  that escape hatch is not a way around the scope rule.
- **Ranges** as `**L12-L20**` when the point spans lines.
- **Sort bullets by line number** within each file.
- **Permalinks** as `https://github.com/<owner>/<repo>/blob/<full-sha>/<path>#L<start>-L<end>`.
  Use the full 40-character SHA — a short SHA or a branch name produces a link
  that rots. Include a line of context either side so the link lands readably.
- **Link to related things** when they'd save the user a click: the earlier PR
  that added the code, the commit that introduced a guard being removed, the
  `CLAUDE.md` rule being broken.
- **Mark repeats inline** with `(already raised by <who> — <link>)` at the end of
  the bullet, rather than adding a fifth tag. Four tags is what keeps the list
  scannable.
- **Drop anything already resolved in the thread** instead of listing it as
  addressed. The exception is a re-review, where the per-comment verdict from
  Step 2 is the point and belongs above the file list.

## Tags

Four, so the list stays scannable:

- `bug` — will behave wrong. Say what breaks.
- `risk` — might break something outside this PR, usually another caller of
  changed shared code.
- `question` — looks deliberate, but the consequence isn't obvious and only the
  author knows. Phrase it as a real question.
- `nit` — style, naming, magic numbers, small cleanups. Safe to ignore.

## Writing the bullets

Aim for something the user can paste onto the PR unedited.

Good: `Drops width: '100%'. Two other files use SearchBar, their layout may shift.`
Weak: `Consider whether the removal of the width property may have unintended consequences for other consumers of this component.`

The first names the change, the effect, and where to look, in fewer words. The
second is hedged and says nothing checkable.

Write for the PR author, not about them. `This clears the filter on remount` not
`You forgot to preserve the filter`.

When you're unsure whether something is real, say so in the bullet — `not sure
if X is reachable, worth a look` is honest and still useful. Don't quietly drop
it, and don't state it as fact.

## Finishing

End with the offer, since they may want it: they can ask you to expand any
bullet into a full paste-ready paragraph, or to post a chosen subset. Posting is
a separate, explicit request — never fold it into this step.
