# Session Handoff Template

> **Purpose.**  When you start a new chat session and want to continue work on
> this repository, paste a filled-in copy of the template at the bottom into
> the new session.  It tells the next agent exactly what's done, what's
> pending, and how to verify changes.
>
> **Why this matters.**  Each chat session is isolated -- a new agent has no
> memory of prior conversations.  The repo state on GitHub is the only
> ground truth that survives.  This file makes the handoff explicit so the
> next agent doesn't (a) miss recent commits, (b) reinvent fixes that
> already shipped, or (c) start from `main` when the live work is on a
> feature branch.

---

## How to fill in the handoff

Before starting a new session, run these locally and paste the output into
the relevant slots in the template:

```bash
git fetch origin
git log --oneline -10                # latest commits on the active branch
git status                            # clean / dirty
git branch --show-current             # active branch
gh pr list                            # open PRs (or check the GitHub UI)
```

Then, for **each pending issue**, write down:

- A one-line summary of the user-visible problem.
- A short note on which file(s) to look at first (it saves the next agent a
  lot of repository spelunking).
- (Optional) Your current best guess at the root cause.

Keep it factual.  Don't editorialise about prior agent behaviour and don't
invent context.  If something is unverified, mark it as a hypothesis.

---

## Trust rules for the next agent

The first thing the next agent should do is **verify the handoff against
the actual repo state** -- branch, latest commit, PR, file presence -- using
the GitHub API or `git log`.  If anything in the handoff doesn't match what
is on disk, the agent should say so before doing any work.  An incorrect
handoff is worse than no handoff.

Specifically:

1. If the handoff says a branch / commit / PR exists, the agent confirms it
   exists.  No silent "let me just go with it" if it doesn't.
2. If the handoff names files, the agent confirms they exist before reading
   line ranges.
3. If the offscreen Qt smoke test fails for environment reasons (missing
   `libGL.so.1`, etc.), the agent doesn't claim success based on it.  The
   user's screenshot is the ground truth on visual issues.
4. The agent should run the existing test suite (`pytest -q`) before
   pushing anything.

---

## Communication conventions used by the user

These are stable across sessions and worth carrying into the new one:

- The user shares **screenshots with red boxes** around problems -- treat
  those as the highest-fidelity signal.
- "Fix this" is a direct instruction.  Don't ask permission; do it, run the
  tests, push to the active feature branch, surface the PR / branch URL.
- The user prefers **minimalist UI** -- don't add features, surface area,
  or copy that wasn't requested.
- Don't merge open PRs.  All work goes to whichever feature branch is
  currently active; `main` is the stable baseline.
- The user is on **Windows**.  Visual issues that are Windows-specific
  (native frame bevels, font rendering) won't reproduce in headless Linux
  Qt; trust the screenshot, not the smoke test.

---

## Template -- copy from here, fill in, paste into the new session

```text
Continue work on Salesforce Translation Manager.

Repository: sourav98hazra/Salesforce-Translation-Handler
Active branch: <branch-name>           # e.g. feat/v1.1-improvements
Latest commit: <short-sha>             # output of `git rev-parse --short HEAD`
Open PR: #<n> (do not merge yet)       # or "none"
Default branch: main (untouched)

What's working
- <bullet describing a stable, shipped feature>
- <bullet>
- <bullet>

Pending issues from previous session
1. <one-line issue title>
   Files to look at first: <path/a.py>, <path/b.py:120-200>
   Hypothesis (unverified): <root cause guess, or "unknown">

2. <next issue>
   Files: ...
   Hypothesis: ...

Verification commands
  cd /path/to/Salesforce-Translation-Handler
  git pull origin <branch-name>
  pip install -e ".[gui,dev]"
  pytest -q                            # must pass

Notes / guard rails
- Do NOT touch main; everything goes to <branch-name>.
- Do NOT merge PR #<n> until the user reviews on Windows.
- Trust user screenshots over offscreen Qt smoke tests for visual bugs.
- The user is on Windows; some Qt rendering only reproduces there.
```

---

## What's currently live (as of v1.5)

Use this as a sanity-check for the next handoff -- the things below are
shipped on `feat/v1.1-improvements` and don't need re-fixing:

- 6-phase pipeline (Import STF / STF -> Excel / Translate / Browse &
  Review / Validate & Fix / Export STF), each phase usable independently
  *or* as part of the end-to-end flow.
- 4 translator backends (Google free / DeepL / Azure / OpenAI) selectable
  in `Edit -> Settings`.
- Translation Memory (SQLite), glossary (CSV), per-component scope filter,
  multi-language batch, adaptive rate limiting, wake-lock.
- 5 themes (light, dark, ocean, forest, sunset) + auto.
- Side-by-side editor in Phase 4 and Phase 5 with a draggable vertical
  splitter that grows the Source / Translation text areas.
- Soft borders, rounded panels, screen-aware window sizing, resizable
  sidebar (220-280 px), `MainWindow` minimum 900x600.
- In-app User Guide (F1) and About dialog (Help menu) -- both render
  through `clamp_to_screen()` so they always fit the display.
- 65 tests passing.
