---
name: security-audit
description: Defensively scan a codebase (or a specific path) for OWASP-style vulnerabilities — injection, path traversal, unsafe reflection/deserialization, SSRF, hardcoded secrets, and XXE — and report each confirmed finding with its file:line location, severity, and concrete remediation. Use when asked to do a security audit, review code for vulnerabilities, find injection/SSRF/secret-exposure risks, or harden a project before release.
argument-hint: [path to scan, optional]
allowed-tools: Read, Glob, Grep, Bash
---

## Security Audit

A **defensive** security review. The goal is to *find and report* vulnerabilities so they can be fixed — never to exploit them. Produce confirmed findings with `file:line`, severity, and remediation. Do not generate exploit payloads, weaponized proof-of-concept code, or instructions for attacking a live system.

This skill is language-agnostic. Patterns below use **Java / Spring** as worked examples; adapt the regexes to the languages actually present in the repo (check file extensions, build files, and framework imports first).

### Scope

- If `$ARGUMENTS` is provided, limit the scan to that file or directory.
- Otherwise scan all source code in the repository.
- Exclude generated output, vendored dependencies, and build artifacts (e.g. `target/`, `build/`, `dist/`, `node_modules/`, `vendor/`, `.git/`).
- For secret-style checks, also distinguish production code from test fixtures and report them separately rather than ignoring tests entirely.

### Method

For each category: grep for the candidate patterns, then **read each hit in context** before reporting. A match is only a finding if untrusted input can actually reach the sink without adequate validation, encoding, or sandboxing. Trace data flow far enough to be confident. Report confirmed issues, not theoretical ones.

### Checks to Perform

#### 1. Injection (SQL / OS command / template / LDAP)
String-concatenated queries or commands built from user input.
- SQL: `Statement`, `createQuery(`, `executeQuery(` / `executeUpdate(` with `+` string building; raw queries interpolating request data.
- OS command: `Runtime.getRuntime`, `ProcessBuilder`, `\.exec\(`, plus shell helpers in other languages (`os.system`, `subprocess`, `child_process`, `eval`, backticks).
- Generic regex: `(createQuery|executeQuery|exec|system|popen)\s*\(.*\+`
Remediation: parameterized queries / prepared statements, argument arrays (no shell), allow-lists. Flag any string concatenation of untrusted input into an interpreter.

#### 2. Path Traversal
File or resource paths built from untrusted input.
- Grep: `new File\(.*\b(get(Name|Parameter|Header)|input|request|param)`, `Path\.of\(.*input`, `Paths\.get\(.*input`, `\.\./`, `FileInputStream\(.*request`
Verify each hit canonicalizes the resolved path and confirms it stays within an intended base directory (e.g. `getCanonicalPath().startsWith(base)`), or rejects `..` / absolute paths.
Remediation: canonicalize and bound-check against an allowed root; reject path separators in user-supplied filenames.

#### 3. Unsafe Reflection / Deserialization
Dynamic type loading or object deserialization driven by input.
- Reflection: `Class\.forName\(.*input`, `getMethod\(.*input`, `\.newInstance\(`, `setAccessible\(true\)`
- Deserialization: `ObjectInputStream`, `readObject\(`, `new Yaml\(\)`, `Yaml\.load\(` (unsafe vs `loadAs`/SafeConstructor), `readValue\(` on polymorphic types with default typing enabled, `XMLDecoder`, `pickle.loads`, `yaml.load` (Python).
Remediation: avoid native deserialization of untrusted data; use type allow-lists, safe parsers (SnakeYAML `SafeConstructor`, Jackson without `enableDefaultTyping`), or schema-validated JSON instead. Never reflect into a class name supplied by a caller.

#### 4. Server-Side Request Forgery (SSRF)
Outbound requests whose URL/host comes from input.
- Grep: `(HttpClient|RestTemplate|WebClient|URL\(|openConnection|requests\.get|fetch\(|HttpURLConnection).*\b(input|param|url|request|host)\b`
Verify the target URL is validated against an allow-list of hosts/schemes and that redirects and internal/metadata addresses (`169.254.169.254`, `localhost`, RFC1918 ranges) are blocked.
Remediation: allow-list destinations, resolve-and-validate the IP, disable automatic redirects, block link-local/private ranges.

#### 5. Hardcoded Secrets
Credentials, tokens, or keys embedded in source or config.
- Grep (case-insensitive): `(password|passwd|secret|token|api[_-]?key|access[_-]?key|private[_-]?key|client[_-]?secret)\s*[:=]`
- Also: `-----BEGIN .*PRIVATE KEY-----`, AWS-style `AKIA[0-9A-Z]{16}`, long base64/hex literals assigned to credential-named variables.
Distinguish real values from placeholders (`changeme`, `${ENV_VAR}`, `***`) and from test fixtures. Report production secrets as higher severity than test ones.
Remediation: move secrets to environment variables or a secrets manager; rotate any exposed credential; add the pattern to secret-scanning / pre-commit hooks.

#### 6. XML External Entity (XXE)
XML parsing without external-entity processing disabled.
- Grep: `DocumentBuilderFactory`, `SAXParserFactory`, `XMLReader`, `TransformerFactory`, `XMLInputFactory`, `SAXBuilder`, `Unmarshaller`
For each, confirm secure configuration: `setFeature("http://apache.org/xml/features/disallow-doctype-decl", true)`, external general/parameter entities disabled, `XMLConstants.FEATURE_SECURE_PROCESSING` enabled, or `IS_SUPPORTING_EXTERNAL_ENTITIES=false`.
Remediation: disable DOCTYPE declarations and external entities on every XML parser factory.

#### Additional: TLS / Certificate Validation Bypass
- Grep: `TrustManager`, `checkServerTrusted`, `HostnameVerifier`, `setHostnameVerifier`, `verify\(.*return true`, `InsecureTrustManager`, `--ignore.*ssl`, `verify=False`
Flag any global disabling of certificate or hostname validation. If a "skip TLS verification" option exists, verify it is opt-in, scoped to a single client, and never affects the global SSL context.

### Report Format

Output a single table, ordered by severity (CRITICAL → HIGH → MEDIUM → LOW):

| Severity | Location | Category | Issue | Remediation |
|----------|----------|----------|-------|-------------|
| CRITICAL | `path/to/File.java:42` | Injection | Concrete description of the data flow | Specific fix |

After the table, add a one-line summary (counts by severity).

Report only confirmed findings with a real, traceable data flow — not theoretical risks. If nothing is found, state: **"No vulnerabilities found."**
