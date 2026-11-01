---
name: auto-commit
description: Analyzes git changes and automatically creates the maximum number of meaningful atomic Conventional Commits with appropriate scopes. Decides staging, verifies changes, protects against accidental credential commits, and keeps repository history granular and traceable. Use when committing changes or organizing repository history.
---

# Auto Commit Skill

## Objective

Analyze all current repository changes and organize them into the **maximum
number of meaningful atomic commits**, strictly following Conventional Commits,
including the `type(scope):` form used across the m4all projects.

The goal is not to minimize commit count.

The goal is to produce the most granular history that still represents real,
independently understandable responsibilities.

Each commit should ideally be independently reviewable and revertible without
creating artificial or meaningless fragmentation.

---

# Commit Standards

Every commit MUST:

- Follow Conventional Commits: `type(scope): subject`
- Be written in **English**
- Use imperative mood:
  - `add`
  - `fix`
  - `remove`
  - `simplify`
  - `prevent`
- Never use past tense:
  - `added`
  - `fixed`
  - `removed`
- Never use gerunds:
  - `adding`
  - `fixing`
  - `removing`
- Keep the subject on a single line whenever possible
- Prefer subjects ≤ 50 characters
- Hard cap subjects at **72 characters**
- Be clear, concise and strictly technical
- Use lowercase after the type/scope prefix
- Never end the subject with a period
- Use an impersonal tone
- Describe a concrete behavior, bug or responsibility
- Never mention authorship, collaboration or AI involvement
- Never add `Co-Authored-By`
- Never add `Generated with`
- Never add tool attribution
- Never add AI attribution
- Never add attribution footers of any kind

Allowed semantic types:

- `feat:` — new behavior
- `fix:` — bug fix
- `refactor:` — behavior-preserving restructuring
- `perf:` — performance improvement
- `style:` — formatting only, without logic changes
- `test:` — tests
- `docs:` — documentation
- `build:` — build system, dependencies or lockfiles
- `ci:` — CI/CD configuration
- `chore:` — configuration or repository housekeeping not covered above

Avoid vague subjects such as:

```text
update things
changes
improvements
melhorias
added stuff
simple change
finished work
misc fixes
fix issues
```

If a subject could describe almost any commit, rewrite it.

Examples:

```text
feat(auth): add password recovery flow
fix(tasks): prevent duplicate task loading
refactor(user): simplify profile mapping
perf(tasks): reduce redundant queries
test(auth): cover expired token handling
build: update next dependencies
```

---

# Commit Anatomy

Default:

```text
type(scope): imperative subject
```

Add a body only when:

- the reason for the change is not evident from the diff
- important implementation context would otherwise be lost
- the change is breaking

Do not create bodies that merely repeat the subject.

Breaking changes:

```text
feat(auth)!: remove legacy token format

BREAKING CHANGE: legacy authentication tokens are no longer accepted
```

The only allowed optional footers are:

```text
BREAKING CHANGE:
Refs:
```

No attribution footer is allowed.

---

# Scope Selection

The scope represents the domain, feature or module affected by the commit.

Derive it from the actual changed path, package or responsibility.

Do not guess.

Examples for Java/Spring:

```text
user
auth
security
ambient
audit
email
position
solicitation
feature-flag
external
contract
config
```

Examples for React/Next.js:

```text
invoices
auth
sidebar
profile
sla
pages
motoboy
correios
tasks
```

Rules:

- Prefer one scope per commit.
- Use lowercase.
- Use kebab-case when necessary.
- Split independent scopes whenever they represent distinct responsibilities.
- Omit the scope only when the change is genuinely repository-wide.

Examples:

```text
build: update dependencies
ci: adjust deployment workflow
chore: configure formatter
```

Multiple directories do not automatically mean multiple commits.

However, when directories represent independently meaningful responsibilities,
prefer splitting them.

---

# Atomic Commit Strategy

The default strategy is:

> Create as many meaningful atomic commits as the change naturally supports.

Do not optimize for the smallest possible number of commits.

Do not squash independent responsibilities merely because they belong to the
same feature branch.

At the same time, do not create meaningless micro-commits whose only purpose is
increasing the commit count.

---

## Split aggressively when responsibilities differ

Prefer separate commits when any of these boundaries exist:

- Different semantic types
- Different independently meaningful scopes
- Feature implementation and unrelated refactoring
- Behavioral changes and unrelated structural cleanup
- Multiple independent bug fixes
- Multiple independent features
- Configuration unrelated to implementation
- Dependency changes unrelated to implementation
- Documentation unrelated to implementation
- Independent migrations
- Independent infrastructure changes
- Separate responsibilities that could reasonably be reviewed independently
- Separate responsibilities that could reasonably be reverted independently

Examples:

```text
refactor(tasks): extract task filters
perf(tasks): reduce task query round-trips
test(tasks): cover paginated task loading
docs(tasks): document pagination behavior
```

This is preferable to:

```text
perf(tasks): improve task module
```

when those responsibilities are genuinely separable.

---

## Keep changes together when separation would be artificial

Do not split tightly coupled pieces whose independent commit would leave an
incomplete, invalid or misleading state.

Examples:

- A feature and the minimum code required to make that feature work
- A dependency introduced exclusively for the implementation using it
- An entity change and the migration required for that same change
- A renamed API contract and all immediately required call-site adaptations
- Generated lockfile changes caused directly by a dependency change
- A regression test whose only purpose is proving a specific bug fix when
  separating it adds no useful historical distinction

Atomicity means logical independence, not arbitrary file separation.

---

# Execution Protocol

## 1. Survey repository state

Run:

```bash
git status --porcelain
git branch --show-current
```

Account for:

- staged files
- unstaged files
- untracked files

Never assume all changes belong together.

Never blindly re-stage an intentionally partial staged set.

---

## 2. Inspect staged and unstaged changes

Inspect:

```bash
git diff
git diff --cached
```

Use additional targeted diffs when necessary:

```bash
git diff -- <path>
git diff --cached -- <path>
```

Understand what each change actually does before grouping it.

Do not categorize only from filenames.

---

## 3. Identify logical responsibilities

For every changed region, determine:

1. semantic type
2. scope
3. responsibility
4. relationship with surrounding changes
5. whether it can stand independently
6. whether it can be reverted independently
7. whether separating it would leave the repository in a misleading or broken
   intermediate state

Use these boundaries to derive the commit plan.

---

## 4. Maximize meaningful atomicity

Split the changes into the maximum number of commits that remain logically
useful.

Prefer another commit when a responsibility is independently understandable.

Avoid splitting when the resulting commit would be:

- incomplete
- non-functional
- misleading
- purely mechanical without historical value
- impossible to review meaningfully in isolation

When uncertain between combining two responsibilities and separating them,
prefer separation **if both resulting commits remain valid and meaningful**.

---

# Staging Strategy

Prefer path-based staging whenever possible:

```bash
git add <path>
```

or:

```bash
git add <path1> <path2>
```

Stage only the files belonging to the responsibility currently being committed.

---

## Partial-file staging

Use:

```bash
git add -p
```

**only when the same file contains changes belonging to more than one genuinely
independent responsibility.**

Do not use `git add -p` merely because:

- a file is large
- many lines changed
- several hunks exist
- splitting could theoretically increase the commit count

Use partial staging only when it produces meaningful responsibility boundaries.

Before partial staging, ensure that each staged subset still forms a coherent
commit together with its related files.

---

# Ignored File Types

Ignore all changed files whose names end in `.md` or `.json`, regardless of
whether they are staged, unstaged or untracked.

Rules:

- Never include `.md` or `.json` files in commit planning.
- Never stage or commit `.md` or `.json` files.
- If one of these files is already staged, unstage it without discarding its
  working-tree changes before creating any commit.
- Leave ignored files unchanged and report them as intentionally uncommitted in
  the final result.

---

# Sensitive File Protection

Before staging or committing, cheaply inspect changed filenames for common
credential or secret files.

Treat the following as suspicious:

```text
.env
.env.*
*.pem
*.key
*.p12
*.pfx
*.jks
*.keystore
credentials*
credential*
secrets*
secret*
service-account*
```

Also treat obviously credential-bearing filenames as suspicious.

Rules:

- Never automatically stage a suspicious untracked or unstaged file.
- If a suspicious file is already staged, stop before committing it.
- Report the suspicious path.
- Do not inspect or print secret values unnecessarily.
- Do not use this check as a full secret scanner.
- Do not perform expensive repository-wide secret scanning unless explicitly
  requested.

This protection exists only to prevent obvious accidental credential commits
with minimal overhead.

---

# Pre-Commit Verification

Before committing a logical group, when a quick project-native check exists,
verify that the change at least compiles or type-checks.

TypeScript / Next.js:

```bash
npm run tc
```

and/or:

```bash
npm run lint
```

Java / Spring:

```bash
./mvnw -q compile
```

Use repository-specific scripts when clearly available.

Guidelines:

- Prefer the cheapest relevant verification.
- Do not invent commands.
- Do not install dependencies solely to perform verification.
- Do not run unrelated expensive suites by default.
- Pure documentation changes normally require no build verification.
- Pure CI/configuration changes may skip application compilation when it does
  not apply.

If verification fails because of the changes being committed:

- fix the issue when it is clearly within the requested work, or
- stop before committing the affected group

Do not intentionally commit a red tree.

Never bypass Git hooks with:

```bash
--no-verify
```

unless explicitly requested by the user.

---

# Type Selection

Choose the type based on the primary nature of each atomic responsibility.

| Change                                 | Type       |
| -------------------------------------- | ---------- |
| New behavior                           | `feat`     |
| Incorrect behavior corrected           | `fix`      |
| Same behavior with different structure | `refactor` |
| Runtime/query/rendering optimization   | `perf`     |
| Formatting only                        | `style`    |
| Test-only responsibility               | `test`     |
| Documentation-only responsibility      | `docs`     |
| Dependencies/build system              | `build`    |
| CI/CD configuration                    | `ci`       |
| General repository maintenance         | `chore`    |

Examples of incorrect classification:

| Wrong                   | Correct                             |
| ----------------------- | ----------------------------------- |
| `config:`               | `chore(config):`, `build:` or `ci:` |
| `style: refactor logic` | `refactor:`                         |
| `feat: fix login error` | `fix(auth): ...`                    |
| `fix: fixes`            | describe the actual bug             |
| `chore: update stuff`   | identify the actual responsibility  |

---

# Commit Execution

For each identified atomic responsibility:

1. Stage only that responsibility.
2. Verify the staged diff.
3. Generate the Conventional Commit message.
4. Validate the message against the Commit Standards.
5. Run the relevant quick pre-commit verification when applicable.
6. Execute the commit.
7. Continue with the next responsibility.

Commit with:

```bash
git commit -m "<message>"
```

Use a multiline commit only when a required body or footer exists.

Never:

- rewrite existing commits
- amend already-pushed commits
- rebase shared history
- force-push
- alter merge commits

unless explicitly requested.

Assume repository history may be shared.

---

# Message Validation

Before every commit, ensure:

- A valid semantic type is used.
- The scope reflects the actual responsibility.
- Scope is omitted only deliberately.
- The subject is English.
- The subject uses imperative mood.
- The subject is concrete.
- The subject has no trailing period.
- The subject is not unnecessarily capitalized.
- The subject is no longer than 72 characters.
- No vague wording is present.
- No unrelated responsibilities are mixed.
- Further meaningful atomic separation was considered.
- Separation was not performed merely for artificial commit count.
- No AI/tool attribution exists.
- No `Co-Authored-By` exists.
- No unauthorized footer exists.
- No obvious credential file is being accidentally committed.

If validation fails, correct the grouping or regenerate the message before
committing.

---

# Final Check

After all planned commits are complete, run only:

```bash
git status --short
```

Do not perform additional final builds, tests, lint or verification passes.

Report:

- each created commit
- its short SHA
- its commit message
- any files intentionally left uncommitted

Example:

```text
a51d821 refactor(tasks): extract task filtering logic
87fd023 perf(tasks): paginate task queries
d271bf9 test(tasks): cover paginated loading

Working tree clean.
```

---

# Decision Principle

For every possible split, ask:

> Does this change represent an independently understandable responsibility that
> can reasonably be reviewed and reverted on its own?

If yes, split it.

Then ask:

> Would separating it create an incomplete, invalid or meaningless intermediate
> commit?

If yes, keep it together.

The desired result is the **maximum useful commit granularity**, not the minimum
commit count and not artificial fragmentation.
