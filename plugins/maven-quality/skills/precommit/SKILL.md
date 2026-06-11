---
name: precommit
description: Run pre-commit quality checks for a Maven/Java project — auto-format, validate Checkstyle/PMD, and run tests before committing. Use before creating a commit, or when asked to verify the working tree is ready to commit.
---

## Pre-commit Check: Format → Validate → Test

Run this before every commit to catch format, style, and test failures early.
Defaults target a Maven/Java project using spring-javaformat, Checkstyle, and
PMD. Adjust module names (`-pl`), profiles, and the `mvn` invocation to match
your project.

> Examples use the Maven wrapper `./mvnw`. If your environment has no wrapper,
> substitute your `mvn` binary, e.g.
> `bash "/path/to/mvn" <goal> -f pom.xml`.
> For multi-module builds, scope steps with `-pl <module>`.

---

### Step 1: Auto-format

```bash
./mvnw spring-javaformat:apply
```

---

### Step 2: Validate (Checkstyle + PMD)

```bash
./mvnw validate 2>&1 | grep -E "^\[ERROR\]|violations|PMD Failure"
```

If violations remain after auto-format, fix them manually (see the `codestyle`
skill). Do **not** proceed to Step 3 until `validate` passes cleanly.

---

### Step 3: Run tests

```bash
./mvnw test 2>&1 | tail -20
```

---

### Step 4: Report outcome

Summarize the result:

| Step | Result |
|------|--------|
| Format | Applied / Already clean |
| Validate | 0 violations / N violations (list them) |
| Tests | X passed, 0 failures / list failures |

- If everything is green, the working tree is ready to commit.
- If formatting changed files, list them so they can be staged.
- If any step fails, report which step failed with the error details, and fix it before committing.
