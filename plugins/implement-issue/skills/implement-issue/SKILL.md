---
name: implement-issue
description: Drive a GitHub issue from branch to pull request — read the issue, create a feature branch, implement the change, run the project's build and tests, then commit, push, and open a PR. Language and build-tool agnostic. Use when asked to implement, fix, or resolve a GitHub issue by number.
argument-hint: "[issue-number]"
disable-model-invocation: true
allowed-tools: Bash(gh *), Bash(git *)
---

## Implement GitHub issue #$ARGUMENTS

Follow this workflow for every code change. It is independent of language and build tool — adapt the build and test commands to whatever the project uses.

### Step 1: Read the issue

```bash
gh issue view $ARGUMENTS
```

Understand the requirements before writing any code. If the issue is ambiguous, note your assumptions.

### Step 2: Create a feature branch

```bash
git checkout main
git pull
git checkout -b feature/$ARGUMENTS-<short-description>
```

Use a concise, hyphenated `<short-description>` derived from the issue title.

### Step 3: Implement the changes

- Read relevant source files before making modifications.
- Follow the project's existing coding standards and conventions (formatting, language version, libraries already in use).
- Keep changes focused on the issue requirements — avoid unrelated refactors.

### Step 4: Build and run tests

Run the project's build and test commands. Discover them from the repo rather than assuming a specific tool — for example a Maven project might use `./mvnw test`, but other projects use Gradle, npm, pytest, go test, etc.

Fix any failures before proceeding.

### Step 5: Commit and push

```bash
git add <changed-files>
git commit -m "<descriptive message>

Closes #$ARGUMENTS

Co-Authored-By: Claude <noreply@anthropic.com>"
git push -u origin HEAD
```

### Step 6: Create the pull request

```bash
gh pr create --title "<concise title>" --body "## Summary
<bullet points of what changed and why>

## Test plan
<how to verify the change>

Closes #$ARGUMENTS

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
```

Report the PR URL when done.

### Git safety

- Never force-push (`git push --force`) or delete branches without explicit confirmation from the user.
- Push to the feature branch only; do not push directly to `main`.
