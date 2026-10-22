# Solo workflow with Claude Code

`$` means your shell. `>` means inside a Claude Code session. Everything else happens on its own.

The idea in one line: you write one sentence, Claude interviews you into a spec, a fresh session builds it and leaves one commit whose message lists every test it ran, you read that commit. A pull request happens only when you decide a branch is a cohesive theme.

## Where the big plan lives

For anything larger than a few features, write the product spec first: `docs/specs/00-product/spec.md`. It is the one document above the feature specs, and it holds the goal, the users, the anti-goals, the architecture decisions with their reasons, and a `## Specs` section: the ordered list of feature specs to build, one checkbox each.

```
> /effort high
> /interview-me-engineering 00-product Ledger: invoicing for freelancers, multi-tenant, Stripe billing, web app.
```

Claude interviews you about users, scope, architecture, and the riskiest unknowns, then proposes the spec list and asks you to confirm it. The result looks like:

```
## Specs
- [ ] 00-skeleton: app runs, one real test, lint, GET /health returns 200
- [ ] 01-auth: user signs up, logs in, sees an empty dashboard
- [ ] 02-invoices: user creates an invoice and sees it listed
- [ ] 03-customers: …
```

From then on:

- `/interview-me-engineering 01-auth …` reads the product spec first and stays inside its decisions. If you ask for something that contradicts it, Claude says so and, on your confirmation, updates the product spec.
- `/implement 01-auth` reads the architecture decisions and anti-goals, builds, and ticks the `01-auth` line in the product spec inside its one commit.
- Progress is `grep "\[ \]" docs/specs/00-product/spec.md`. The ticked lines are what shipped; git shows when.

The product spec changes only through an interview or your own edit. Implementation sessions may tick a box and nothing else. Small projects skip it and start at `00-skeleton`.

## First spec vs every spec after

The manual work is front-loaded into the first spec. From the second spec on, you type three commands per feature and everything else runs by itself.

| | First spec (skeleton) | Every spec after |
| --- | --- | --- |
| You type | `/interview-me-engineering 00-skeleton …`, `/clear`, `/implement 00-skeleton`, then `/run-skill-generator`, `/verify`, `git commit --amend --no-edit` | `/interview-me-engineering NN-…`, `/clear`, `/implement NN-…` |
| Baseline check | Skipped, nothing to run yet | Automatic: `/implement` starts the app with the recorded `run-<name>` skill before changing anything |
| Tests and lint | Claude runs them | Claude runs them |
| End-to-end proof | Claude improvises it from the spec | Claude follows the recorded `verify` skill |
| Pre-commit verify | Not possible yet, no recipe | Automatic: Claude Code runs the project `verify` skill before every commit, because a skill named `verify` now exists (v2.1.286+) |
| Code review | `/code-review`, automatic | `/code-review`, automatic |
| Evidence | Commit body, `Verified` and `Not verified` | Same |
| You review | `git log -1`, the notes, `git show --stat HEAD` | Same |

Why the second column is automatic: `/run-skill-generator` and the bundled `/verify` can only be started by you, but the files they write under `.claude/skills/` are ordinary project skills that Claude loads and runs on its own. If the way the app starts changes later, run `/run-skill-generator` once more and the automation picks up the new recipe.

## Greenfield, step by step

Example: a new app called `ledger`.

### Day 0, set up (10 minutes)

**1. You type**

```
$ mkdir ledger && cd ledger && git init
$ cp -r ~/orca/projects/local-setup/project-template/. .
$ git add -A && git commit -m "Add Claude Code workflow"
$ git switch -c setup
$ claude
```

**What happens:** the repo now has `CLAUDE.md`, three commands in `.claude/commands/`, and `docs/specs/README.md`. No code. You are on a branch called `setup`. Claude Code starts in auto mode and reads `CLAUDE.md`.

**2. You type**

```
> /effort high
> /interview-me-engineering 00-product <one sentence on the whole product>     # big build; skip for a small one
> /clear
> /interview-me-engineering 00-skeleton App runs, one real test passes, lint runs, one end-to-end check is green.
```

**What happens:** the skeleton interview reads `docs/skeleton-checklist.md`, twelve sourced recommendations for a verifiable foundation (compose with health checks, one stack per worktree, bootstrap and smoke commands, strict types, targeted tests, one end-to-end path per feature, agent access to the database and logs, logging rules, pre-commit gates, fail-loud rules, optional boundary lint and review standards). It decides adopt, adapt or skip per item for your stack and records each decision in the spec. If you wrote a product spec, it already knows the stack and data model, so it only asks what is left. Otherwise Claude creates `docs/specs/00-skeleton/spec.md` containing your sentence, then asks you questions one at a time in a pop-up: language and framework, package manager, database, how the app will be deployed, what the one end-to-end check is (a `/health` endpoint, a CLI command). It asks architecture questions first. When it has enough it shows you an outline and asks you to confirm, then writes the spec with five sections: goal, what the user can do and the command that shows it, anti-goals, files and interfaces, verification step.

**You check:** open `docs/specs/00-skeleton/spec.md`. Edit anything you disagree with by hand. This is the only moment the plan is cheap to change.

**3. You type**

```
> /clear
> /effort medium
> /implement 00-skeleton
```

**What happens, unattended, 10 to 30 minutes:**

1. Reads the spec in full, and the product spec if there is one.
2. Tries to start the existing app to check the baseline. There is nothing to run yet, so it moves on.
3. Scaffolds the project: package manifest, folder layout, one real test, lint config, the health check.
4. Writes `docs/specs/00-skeleton/implementation-notes.md` as it goes: every decision the spec did not cover, every tradeoff.
5. Runs the test command and lint until green.
6. Starts the app itself and performs the spec's end-to-end step: hits the health check, captures the real response. Tests alone do not count.
7. Runs `/code-review`: a separate fresh-context reviewer reads the diff and reports bugs. Claude fixes the ones that matter and lists skipped ones in the notes.
8. Squashes everything into one commit on `setup`. Stops. It does not push.

**You check**

```
$ git log -1
```

The commit body looks like this:

```
Add project skeleton (spec: docs/specs/00-skeleton/spec.md)

Verified
- pnpm test: 1 passed, 0 failed
- pnpm lint: clean
- end-to-end: pnpm dev, GET http://localhost:3000/health -> 200 {"ok":true}

Not verified
- Production build on Linux (dev machine only)

Notes: docs/specs/00-skeleton/implementation-notes.md
```

Then `cat docs/specs/00-skeleton/implementation-notes.md` for the decisions, and `git show --stat HEAD` to see which files exist now.

**4. You type**

```
> /run-skill-generator
> /verify
```

**What happens:** these two are bundled skills that only you can start; Claude cannot call them from inside `/implement`. `/run-skill-generator` installs and starts the app from a clean state, records the exact commands and env vars that worked, and writes `.claude/skills/run-ledger/SKILL.md`. `/verify` drives the health check and records its own recipe to `.claude/skills/verify/SKILL.md`. From now on every session uses these recipes instead of guessing, and Claude Code runs the project `verify` skill on its own before each commit.

Delete the `Commands` section from `CLAUDE.md`, since the run skill replaces it, then fold all of it into the skeleton commit:

```
$ git add -A && git commit --amend --no-edit
```

Amending is safe here: nothing has been pushed, and it keeps the rule of one commit per spec. Setup is done. Five things you typed, one commit on `setup`.

### Every feature after that (repeat)

**5. You type**

```
> /clear
> /effort high
> /interview-me-engineering 01-invoices Users can create an invoice and see a list of their invoices.
```

**What happens:** same interview as step 2, now about this feature: data model, validation, what the list shows, what is out of scope, and the end-to-end check (for example "POST /invoices then GET /invoices returns it"). Spec written to `docs/specs/01-invoices/spec.md`.

**You check:** read and edit the spec.

**6. You type**

```
> /clear
> /effort medium
> /implement 01-invoices
```

**What happens:** same as step 3, but now step 2 of the chain matters: Claude starts the app with the recorded run recipe and confirms the baseline is healthy before any change. Then build, notes, tests, the spec's end-to-end step against the real endpoint, the project `verify` skill, `/code-review`, one squashed commit. Stops. No push.

**7. You review**

```
$ git log -1
$ cat docs/specs/01-invoices/implementation-notes.md
$ git show --stat HEAD
```

Read the `Verified` list first. Claude already ran the project `verify` skill before committing; this list is its output, so you are reading the verification, not repeating it. If a test count went down or something is in `Not verified` that should not be, that is your finding. Open the diff only for the files that matter (the data model, the migration, the auth check). One optional extra pass:

```
> /code-review high HEAD~1..HEAD   # your own fresh-context review of this one commit
```

Want to see it with your own eyes for a UI change? Start the app from Orca and click through. No Claude command needed.

**Not ok?** Stay in the session:

```
> The list endpoint returns other users' invoices. Fix it, squash into the same commit, update the Verified list.
```

**Ok?** Go to step 5 with `02-...`. Every `/clear` is the context reset; the spec, the notes, and git carry everything forward.

### Shipping the theme

When `setup` holds the skeleton plus enough features to be a cohesive thing, and only then:

**8. You type**

```
> /code-review ultra               # optional: cloud review of the whole branch against main
> /commit-push-pr
```

**What happens:** commits any leftovers, pushes `setup`, opens one pull request whose body merges the `Verified` and `Not verified` lists from every commit on the branch and links the implementation notes.

**9. You type**

```
$ gh pr merge --squash --delete-branch      # or merge in Orca's PR view
$ git switch main && git pull
$ git switch -c billing                      # next theme
```

### What the repo looks like after two features

```
ledger/
├── CLAUDE.md                          short; Mistakes section grows over time
├── .claude/
│   ├── commands/                      interview-me-engineering, implement, commit-push-pr
│   └── skills/
│       ├── run-ledger/SKILL.md        written by /run-skill-generator
│       └── verify/SKILL.md            written by /verify
├── docs/skeleton-checklist.md         sourced recommendations the skeleton interview walks
├── docs/specs/
│   ├── 00-product/   spec.md                 the big plan; Specs list with ticked boxes
│   ├── 00-skeleton/  spec.md  implementation-notes.md
│   ├── 01-invoices/  spec.md  implementation-notes.md
│   └── 02-customers/ spec.md  implementation-notes.md
└── src/ …                             the app
```

Three commits on the branch, one per spec, each with its evidence.

## Open source into SaaS, what differs

Same loop. Four differences, all before the first feature.

**1. You type**

```
$ git clone <your-fork-url> && cd <repo>
$ git remote add upstream <original-url>
$ cp -r ~/orca/projects/local-setup/project-template/. .
$ git add -A && git commit -m "Add Claude Code workflow"
$ git switch -c saas-core
$ claude
> /run-skill-generator
> /verify
```

**What happens:** `/run-skill-generator` comes first here, because an unfamiliar codebase is exactly where Claude cannot guess how to launch the app. It records the recipe to `.claude/skills/run-<name>/`; `/verify` records its own to `.claude/skills/verify/`. Commit both before anything else, so the first spec commit stays clean:

```
$ git add -A && git commit -m "Record run and verify recipes"
```

**2. You type**

```
> Where do auth, config, database, migrations, tests and deploy live? What does the licence allow?
  Write the answers with file paths into docs/specs/00-saas-layer/spec.md under a Context heading.
```

**What happens:** Claude reads the codebase and writes a map. No code changes.

**3. You type**

```
> /clear
> /effort high
> /interview-me-engineering 00-saas-layer
```

**What happens:** the interview reads the Context you just had written and asks the questions that decide the fork's shape: which upstream files are off limits, where your code lives (its own package or layer is the default), tenancy, auth, billing, deploy. These go into the spec as anti-goals and interfaces.

**4.** `/clear`, `/effort medium`, `/implement 00-saas-layer`, review, then features `01-…` exactly as in greenfield steps 5 to 9.

Periodically, on `main`:

```
$ git fetch upstream && git merge upstream/main
```

## Diagrams

### Branches and commits

```
main ──●───────────────────────────────────────────────────●──────────▶
        \  $ git switch -c <theme>                        /  $ gh pr merge --squash
         \                                               /
          ●─────────●─────────────●─────────────●───────●   theme branch
          │         │             │             │       │
          │     spec 01       spec 02       spec 03     > /commit-push-pr
          │   1 commit       1 commit       1 commit    (only when you say so)
          │   body:          body:          body:
          │   Verified …     Verified …     Verified …
          │   Not verified … Not verified … Not verified …
          │
     template commit      ◀── you review here: $ git log -1
```

### One spec, start to finish

```
 ┌─────────────────────────── SPEC (session 1) ────────────────────────────┐
 │ > /effort high                                                           │
 │ > /interview-me-engineering NN-<feature> one sentence on what the user can do           │
 │        creates docs/specs/NN-<feature>/spec.md                           │
 │        Claude asks one question ──▶ you answer ──▶ … ──▶ spec.md written │
 │ you read spec.md and edit it by hand                                     │
 └──────────────────────────────────┬───────────────────────────────────────┘
                                    │  > /clear
                                    ▼
 ┌───────────────────────── IMPLEMENT (session 2) ─────────────────────────┐
 │ > /effort medium                                                         │
 │ > /implement NN-<feature>                                                │
 │                                                                          │
 │   start app, baseline ──▶ build ──▶ implementation-notes.md              │
 │       ──▶ end-to-end step on the running app ──▶ /code-review ① reviewer │
 │       ──▶ fix findings ──▶ squash ──▶ ONE commit                         │
 │   commit body = Verified (cmd + result) / Not verified (why)             │
 │   never pushes, never opens a PR                                         │
 └──────────────────────────────────┬───────────────────────────────────────┘
                                    ▼
 ┌──────────────────────────── REVIEW (you) ───────────────────────────────┐
 │ $ git log -1                                   evidence                  │
 │ $ cat docs/specs/NN-<feature>/implementation-notes.md   decisions        │
 │ $ git show --stat HEAD                         diff, critical files only │
 │ optional  > /code-review high HEAD~1..HEAD     ② reviewer, your own pass │
 └───────────────┬─────────────────────────────────────────┬────────────────┘
          not ok │                                         │ ok
                 ▼                                         ▼
   > "X is wrong. Fix it, squash into the        > /clear
      same commit, update the evidence."         next spec NN+1 ──▶ SPEC
                                                 theme cohesive ──▶ SHIP
```

### Ship a theme

```
 ┌──────────────────────────── SHIP (branch is cohesive) ──────────────────┐
 │ optional  > /code-review ultra            ③ reviewer, cloud, whole branch│
 │           > /commit-push-pr              PR body built from commit bodies│
 │ $ gh pr merge --squash --delete-branch    or merge in Orca's PR view     │
 │ $ git switch main && git pull                                            │
 │ $ git switch -c <next-theme>                                             │
 └──────────────────────────────────────────────────────────────────────────┘
```

## Reviewer: when and which

| When | What | Who runs it |
| --- | --- | --- |
| Inside every `/implement` | `/code-review` on the session's diff, fresh forked context | Claude, automatic |
| After each commit, optional | `/code-review high HEAD~1..HEAD` | You |
| Before shipping a theme, optional | `/code-review ultra` on the whole branch, cloud, multi-agent | You |
| On the PR, if on Team or Enterprise | Claude Code Review GitHub app, tuned by `REVIEW.md` | Automatic |

## When Claude gets something wrong

Do not correct it in chat. Type:

```
> Write that into CLAUDE.md under Mistakes, or into a skill if it is a procedure.
```

Monthly: `> /doctor` to prune `CLAUDE.md`, skills, and hooks.

## Small change, no spec

```
> Fix X. Verify against the running app. One commit; body lists what you ran and the results.
```

## Commands cheat sheet

| Type | Does | Where it comes from |
| --- | --- | --- |
| `/interview-me-engineering 00-product <one sentence>` | The big plan: users, anti-goals, architecture decisions, ordered Specs list | Template |
| `/interview-me-engineering <name> <one sentence>` | Create `docs/specs/<name>/spec.md`, interview you, write the spec inside the product spec's decisions | Template |
| `/implement <name>` | Baseline run, build, notes, end-to-end proof, `/code-review`, one evidence commit | Template |
| `/commit-push-pr` | Commit leftovers, push, PR body from commit evidence | Template, copied from the Claude Code repo |
| `/run-skill-generator` | Record how to install and run the app | Bundled in Claude Code |
| `/run`, `/verify` | Launch the app; prove a change against the running app. Only you can start these; the first `/verify` records a project skill that Claude then runs before every commit | Bundled |
| `/code-review [effort] [range]` | Fresh-context bug review; `ultra` runs in the cloud | Bundled |
| `/effort low\|medium\|high` | Set effort for the session | Built in |
| `/clear` | New context; use between specs | Built in |
| `/doctor` | Prune CLAUDE.md, skills, hooks | Bundled |

## Sources

Interview prompt and implementation notes: Thariq Shihipar (Claude Code team), 2026. Run-the-app verification, mistakes into CLAUDE.md, no plan mode: Boris Cherny, "Reflecting on a year of Claude Code", 8 June 2026. `/commit-push-pr`: `anthropics/claude-code` repo. Bundled skills: code.claude.com docs. Evidence in commits, PR per theme, squash per spec: your rules.
