---
name: security-audit
description: Defensively scan a codebase (or a specific path) for OWASP-style vulnerabilities — injection, path traversal, unsafe reflection/deserialization, SSRF, hardcoded secrets, and XXE — and report each confirmed finding with its file:line location, severity, and concrete remediation. Use when asked to do a security audit, review code for vulnerabilities, find injection/SSRF/secret-exposure risks, or harden a project before release.
argument-hint: [path to scan, optional]
allowed-tools: Read, Glob, Grep, Bash
---

## Security Audit

> **Try it:** `/security-audit:security-audit src/` — or say "do a security audit of the auth module". The path argument is optional.

A **defensive** security review. The goal is to *find and report* vulnerabilities so they can be fixed — never to exploit them. Produce confirmed findings with `file:line`, severity, and remediation. Do not generate exploit payloads, weaponized proof-of-concept code, or instructions for attacking a live system.

The method is the same in every language; only the sinks differ. So the first step is to find out what the repo is written in.

### Step 1 — Identify the languages

Count source files by extension inside the scope (`git ls-files | sed 's/.*\.//' | sort | uniq -c | sort -rn | head`), and check the manifests (`pom.xml`, `build.gradle`, `package.json`, `pyproject.toml`, `go.mod`, `Cargo.toml`, `*.csproj`, `Gemfile`, `composer.json`). Most repos have more than one: a service plus a front end, plus shell and CI config.

Then read [references/sinks.md](references/sinks.md) and use **only the sections for the languages actually present**. It has the dangerous calls, a grep per check, and the safe form to recommend, for Java/Kotlin, Python, JavaScript/TypeScript, Go, C#/.NET, Ruby, PHP and Rust, plus shell, Dockerfiles and CI workflows. Do not run one language's patterns over another's code: `Runtime.getRuntime` finds nothing in a Python repo, and a scan that matched nothing because it asked the wrong question must not be reported as clean.

A language that is present but has no section still gets audited: apply the check's *concept* below and search for that language's equivalent calls. Say in the report that it was done without a pattern set.

### Scope

- If `$ARGUMENTS` is provided, limit the scan to that file or directory.
- Otherwise scan all source code in the repository.
- Exclude generated output, vendored dependencies, and build artifacts (e.g. `target/`, `build/`, `dist/`, `node_modules/`, `vendor/`, `.git/`).
- For secret-style checks, also distinguish production code from test fixtures and report them separately rather than ignoring tests entirely.

### Method

For each category: grep for the candidate patterns, then **read each hit in context** before reporting. A match is only a finding if untrusted input can actually reach the sink without adequate validation, encoding, or sandboxing. Trace data flow far enough to be confident. Report confirmed issues, not theoretical ones.

### Checks to Perform

Each check is a question about data flow. The patterns in `references/sinks.md` find *candidates*; the question decides whether one is a finding.

#### 1. Injection (SQL / OS command / template / LDAP / NoSQL)
Does untrusted input reach an interpreter as part of the code, rather than as a parameter? Look for queries and commands assembled by concatenation, interpolation or formatting; shell invocation with a single string; templates rendered from user-controlled source; `eval`-style calls.
Remediation: parameterized queries, argument arrays with no shell, allow-lists, sandboxed or precompiled templates.

#### 2. Path Traversal
Does a file or resource path include untrusted input without being resolved and checked against an allowed root? Includes archive extraction ("zip slip") and file uploads that keep the client's filename.
Remediation: resolve to a canonical/absolute path, confirm it stays inside the intended base directory, reject separators and `..` in user-supplied names.

#### 3. Unsafe Deserialization / Dynamic Loading
Is untrusted data handed to a deserializer that can construct arbitrary types, or used to pick a class, module or function to load? Native object formats (Java serialization, `pickle`, `Marshal`, PHP `unserialize`, .NET `BinaryFormatter`) and YAML loaders in their unsafe mode are the usual cases.
Remediation: data-only formats with schema validation, safe loader modes, explicit type allow-lists.

#### 4. Server-Side Request Forgery (SSRF)
Does the server make an outbound request to a URL or host that comes from input? Verify the target is checked against an allow-list of hosts and schemes, that redirects are not followed blindly, and that internal and metadata addresses (`169.254.169.254`, `localhost`, private ranges) are blocked *after* DNS resolution.
Remediation: allow-list destinations, resolve-and-validate the IP, disable automatic redirects.

#### 5. Hardcoded Secrets
Credentials, tokens or keys in source or config. This check is the same in every language:
- Grep (case-insensitive): `(password|passwd|secret|token|api[_-]?key|access[_-]?key|private[_-]?key|client[_-]?secret)\s*[:=]`
- Also: `-----BEGIN .*PRIVATE KEY-----`, AWS-style `AKIA[0-9A-Z]{16}`, long base64/hex literals assigned to credential-named variables, and `.env` files or CI variables committed with real values.
Distinguish real values from placeholders (`changeme`, `${ENV_VAR}`, `***`) and from test fixtures. Report production secrets as higher severity than test ones.
Remediation: environment variables or a secrets manager; rotate anything exposed (removing it from the file does not un-leak it); add the pattern to secret scanning.

#### 6. XML External Entity (XXE)
Is XML parsed with external entities or DOCTYPE processing left on? Defaults differ by language and library version — some are safe out of the box and some are not — so check the configuration at each parser, not only that a parser is used.
Remediation: disable DOCTYPE declarations and external entities on every parser; prefer a hardened parser library.

#### 7. TLS / Certificate Validation Bypass
Is certificate or hostname verification switched off? Flag any global disabling. If a "skip TLS verification" option exists, verify it is opt-in, scoped to a single client, and never touches the process-wide default.

#### 8. Cross-Site Scripting and unsafe output (when the repo renders HTML)
Does untrusted input reach HTML, a template or the DOM without the framework's escaping? Look for the explicit escape hatches — raw/unescaped template output, `innerHTML`-style sinks, "mark safe" helpers.
Remediation: keep auto-escaping on; sanitize with a maintained library where raw HTML is truly required.

### Report Format

Output a single table, ordered by severity (CRITICAL → HIGH → MEDIUM → LOW):

| Severity | Location | Category | Issue | Remediation |
|----------|----------|----------|-------|-------------|
| CRITICAL | `path/to/file.ext:42` | Injection | Concrete description of the data flow | Specific fix |

After the table, add a one-line summary (counts by severity).

Before the table, state the **coverage**: which languages were found, which pattern sets were used, and anything in scope that was not audited (a language with no pattern set, generated code, a directory too large to read). A reader must be able to tell "audited and clean" from "not looked at".

Report only confirmed findings with a real, traceable data flow — not theoretical risks. If nothing is found, state: **"No vulnerabilities found"** — and name what that covers, as above.
