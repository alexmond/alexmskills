# Sinks by language

Patterns for the checks in SKILL.md, one section per language. Use only the
sections for languages present in the repo.

Every pattern finds **candidates**. A match is a finding only when untrusted
input can reach the call without adequate validation — read each hit in context.
The patterns are deliberately broad; expect most hits to be safe.

## Contents

- [Java and Kotlin](#java-and-kotlin)
- [Python](#python)
- [JavaScript and TypeScript](#javascript-and-typescript)
- [Go](#go)
- [C# and .NET](#c-and-net)
- [Ruby](#ruby)
- [PHP](#php)
- [Rust](#rust)
- [Shell, Dockerfiles and CI](#shell-dockerfiles-and-ci)
- [Where untrusted input comes from](#where-untrusted-input-comes-from)

## Java and Kotlin

| Check | Grep | Safe form |
|---|---|---|
| SQL injection | `createQuery\(`, `createNativeQuery\(`, `executeQuery\(`, `executeUpdate\(`, `Statement\b`, `JdbcTemplate` calls with `+` or `String.format` | `PreparedStatement` / named parameters; Criteria or a query builder |
| Command injection | `Runtime\.getRuntime`, `ProcessBuilder`, `\.exec\(` | `ProcessBuilder` with an argument list, no `sh -c` |
| Template / expression | `SpelExpressionParser`, `parseExpression\(`, `ScriptEngine`, `Velocity.evaluate`, OGNL | never evaluate user-supplied expressions; `SimpleEvaluationContext` |
| Path traversal | `new File\(`, `Paths\.get\(`, `Path\.of\(`, `FileInputStream\(`, `ZipEntry`/`getName\(\)` in extraction | `toRealPath()` / `getCanonicalPath()` then `startsWith(base)` |
| Deserialization | `ObjectInputStream`, `readObject\(`, `XMLDecoder`, `new Yaml\(\)`, `enableDefaultTyping`, `@JsonTypeInfo\(use = .*CLASS` | JSON with explicit types; SnakeYAML `SafeConstructor`; `ObjectInputFilter` |
| Dynamic loading | `Class\.forName\(`, `getMethod\(`, `\.newInstance\(`, `setAccessible\(true\)` | fixed allow-list of class names |
| SSRF | `RestTemplate`, `WebClient`, `HttpClient`, `new URL\(`, `openConnection`, `OkHttpClient` | host allow-list, redirects off |
| XXE | `DocumentBuilderFactory`, `SAXParserFactory`, `XMLInputFactory`, `TransformerFactory`, `SAXBuilder`, `Unmarshaller`, `XMLReader` | `disallow-doctype-decl` true; `FEATURE_SECURE_PROCESSING`; `IS_SUPPORTING_EXTERNAL_ENTITIES` false |
| TLS bypass | `TrustManager`, `checkServerTrusted`, `HostnameVerifier`, `verify\(.*return true`, `TrustAllStrategy`, `NoopHostnameVerifier` | default trust store; pin per client if needed |
| XSS | `th:utext`, `<%=` in JSP without `c:out`/`fn:escapeXml`, `@ResponseBody` returning concatenated HTML | `th:text`, `c:out`, an HTML sanitizer |

## Python

| Check | Grep | Safe form |
|---|---|---|
| SQL injection | `\.execute\(\s*f["']`, `\.execute\(.*(%\|\+\|\.format\()`, `\.raw\(`, `\.extra\(`, `text\(\s*f["']` | `execute(sql, params)`; ORM filters; SQLAlchemy bound parameters |
| Command injection | `os\.system\(`, `os\.popen\(`, `subprocess\.[a-z_]+\(.*shell\s*=\s*True`, `commands\.getoutput` | `subprocess.run([...])` with a list and no shell |
| Code / template | `\beval\(`, `\bexec\(`, `compile\(`, `__import__\(`, `render_template_string\(`, `Template\(.*request`, `jinja2\.Environment\(` without `autoescape` | no `eval` on input; `ast.literal_eval`; sandboxed or file-based templates |
| Path traversal | `open\(`, `os\.path\.join\(.*request`, `send_file\(`, `send_from_directory\(`, `tarfile.*extractall`, `zipfile.*extractall`, `shutil\.` | `Path(base, name).resolve()` then `is_relative_to(base)`; `extractall(filter="data")` |
| Deserialization | `pickle\.loads?\(`, `cPickle`, `marshal\.loads?\(`, `shelve\.`, `yaml\.load\((?!.*Safe)`, `jsonpickle`, `dill\.` | `json`; `yaml.safe_load`; never unpickle untrusted bytes |
| Dynamic loading | `importlib\.import_module\(`, `getattr\(.*request`, `globals\(\)\[` | fixed dispatch table |
| SSRF | `requests\.(get\|post\|request)\(`, `urllib\.request\.urlopen\(`, `httpx\.`, `aiohttp.*\.get\(`, `urllib3` | host allow-list; `allow_redirects=False` |
| XXE | `xml\.etree`, `lxml\.etree\.(parse\|fromstring\|XMLParser)`, `xml\.dom\.minidom`, `xml\.sax`, `xmltodict` | `defusedxml`; lxml `resolve_entities=False, no_network=True` |
| TLS bypass | `verify\s*=\s*False`, `_create_unverified_context`, `CERT_NONE`, `check_hostname\s*=\s*False`, `disable_warnings\(` | leave verification on; pass a CA bundle |
| XSS | `\|\s*safe\b`, `mark_safe\(`, `Markup\(`, `autoescape\s*=\s*False`, `HttpResponse\(.*request` | keep autoescape; `bleach`/`nh3` for raw HTML |

## JavaScript and TypeScript

| Check | Grep | Safe form |
|---|---|---|
| SQL / NoSQL injection | `\.query\(\s*` followed by a template literal or `+`, `\.raw\(`, `\$queryRawUnsafe`, `sequelize\.query\(`, `\$where`, `find\(\s*req\.(body\|query)` | placeholders (`?`, `$1`); tagged `$queryRaw`; validate shape before passing objects to Mongo |
| Command injection | `child_process`, `\bexec\(`, `execSync\(`, `spawn\(.*shell:\s*true` | `execFile` / `spawn` with an argument array |
| Code / template | `\beval\(`, `new Function\(`, `setTimeout\(\s*["'\x60]`, `vm\.runIn`, `require\(.*req\.` | no dynamic code from input |
| Path traversal | `fs\.(readFile\|createReadStream\|writeFile\|unlink)`, `path\.join\(.*req\.`, `res\.sendFile\(`, `express\.static` with user input, archive extraction | `path.resolve(base, name)` then `startsWith(base + path.sep)`; `sendFile(name, { root })` |
| Deserialization | `node-serialize`, `serialize-javascript` used to parse, `js-yaml` `\.load\(` on old versions, `unserialize\(` | `JSON.parse` plus schema validation (zod, ajv) |
| Prototype pollution | recursive merge / `Object\.assign\(` / `_.merge\(` / `set\(` fed from `req.body`, keys `__proto__` / `constructor` | reject those keys; `Object.create(null)`; a maintained merge |
| SSRF | `fetch\(`, `axios`, `got\(`, `http\.request\(`, `node-fetch`, `undici` with a URL from input | host allow-list; `redirect: 'manual'` |
| XXE | `libxmljs` with `noent:\s*true`, `xml2js`, `fast-xml-parser`, `DOMParser` server-side | `noent: false`; do not expand entities |
| TLS bypass | `rejectUnauthorized:\s*false`, `NODE_TLS_REJECT_UNAUTHORIZED` | leave on; supply `ca` |
| XSS | `innerHTML`, `outerHTML`, `document\.write`, `insertAdjacentHTML`, `dangerouslySetInnerHTML`, `v-html`, `\[innerHTML\]`, `bypassSecurityTrust`, `res\.send\(.*req\.` | `textContent`; framework binding; DOMPurify |
| Open redirect | `res\.redirect\(.*req\.`, `location(\.href)?\s*=.*(search\|hash\|params)` | allow-list of paths or hosts |

## Go

| Check | Grep | Safe form |
|---|---|---|
| SQL injection | `fmt\.Sprintf\(.*(SELECT\|INSERT\|UPDATE\|DELETE)`, `\.(Query\|Exec\|QueryRow)(Context)?\(.*\+`, `\.Raw\(` | placeholders with args (`db.Query(sql, a, b)`) |
| Command injection | `exec\.Command\(\s*"(sh\|bash\|cmd)"`, `exec\.Command\(.*\+` | `exec.Command(name, args...)`, no shell |
| Template | `text/template` used for HTML, `template\.HTML\(`, `template\.JS\(`, `template\.URL\(` | `html/template`; no type conversions on input |
| Path traversal | `os\.(Open\|ReadFile\|Create\|WriteFile)`, `filepath\.Join\(`, `http\.ServeFile\(`, `archive/(zip\|tar)` extraction | `filepath.Clean` then check with `filepath.Rel` / prefix; `os.Root` (Go 1.24+) |
| Deserialization | `encoding/gob`, `yaml\.Unmarshal` into `interface{}`, `json\.Unmarshal` into `interface{}` then type-switched | decode into concrete structs; `DisallowUnknownFields` |
| SSRF | `http\.(Get\|Post\|NewRequest)`, `client\.Do\(` | allow-list; custom `DialContext` rejecting private IPs; `CheckRedirect` |
| XXE | `encoding/xml` does not expand external entities; check any cgo `libxml2` binding instead | — |
| TLS bypass | `InsecureSkipVerify:\s*true` | default `tls.Config`; `RootCAs` |
| Other | `unsafe\.`, ignored errors on security calls (`_ =` / `_, _ =`), `math/rand` for tokens | `crypto/rand` for anything secret |

## C# and .NET

| Check | Grep | Safe form |
|---|---|---|
| SQL injection | `SqlCommand\(.*(\+\|\$")`, `FromSqlRaw\(`, `ExecuteSqlRaw\(`, `CommandText\s*=.*\+` | `SqlParameter`; `FromSqlInterpolated`; LINQ |
| Command injection | `Process\.Start\(`, `ProcessStartInfo`, `UseShellExecute\s*=\s*true` | `ArgumentList`, no shell |
| Path traversal | `File\.(Open\|Read\|Write\|Delete)`, `Path\.Combine\(` (an absolute second argument replaces the first), `PhysicalFile\(`, `ZipFile.*Extract` | `Path.GetFullPath` then `StartsWith(root)` |
| Deserialization | `BinaryFormatter`, `SoapFormatter`, `NetDataContractSerializer`, `LosFormatter`, `ObjectStateFormatter`, `TypeNameHandling\.(All\|Auto\|Objects)`, `JavaScriptSerializer` with a type resolver | `System.Text.Json`; `TypeNameHandling.None` |
| Dynamic loading | `Type\.GetType\(`, `Activator\.CreateInstance\(`, `Assembly\.Load` | allow-list |
| SSRF | `HttpClient`, `WebClient`, `WebRequest\.Create\(` | allow-list; `AllowAutoRedirect = false` |
| XXE | `XmlDocument`, `XmlTextReader`, `XmlReaderSettings`, `DtdProcessing\.Parse`, `XmlResolver\s*=` (old framework versions default unsafe) | `DtdProcessing.Prohibit`; `XmlResolver = null` |
| TLS bypass | `ServerCertificateValidationCallback`, `ServerCertificateCustomValidationCallback`, `DangerousAcceptAnyServerCertificateValidator` | default validation |
| XSS | `Html\.Raw\(`, `MarkupString`, `@Html\.Raw`, `Response\.Write\(` | Razor's default encoding |

## Ruby

| Check | Grep | Safe form |
|---|---|---|
| SQL injection | `where\(\s*["'].*#\{`, `find_by_sql`, `\.order\(\s*params`, `\.pluck\(\s*params`, `connection\.execute\(` | hash or `?` conditions; `sanitize_sql` |
| Command injection | backticks, `%x\(`, `system\(\s*["']`, `exec\(`, `IO\.popen\(`, `Open3`, `Kernel#open` / `open\(` with input (a leading pipe runs a command) | `system(cmd, arg1, arg2)` — separate arguments; `File.open` |
| Code / template | `\beval\(`, `instance_eval`, `class_eval`, `send\(\s*params`, `public_send\(\s*params`, `constantize`, `ERB\.new\(.*params`, `render\s+inline:` | fixed dispatch; never build templates from input |
| Path traversal | `File\.(read\|open\|join)`, `send_file\(`, `render\s+file:` | `File.expand_path` then prefix check |
| Deserialization | `Marshal\.load`, `YAML\.load\(` (unsafe before Psych 4), `YAML\.unsafe_load`, `Oj\.load` in object mode | `JSON.parse`; `YAML.safe_load` |
| SSRF | `Net::HTTP`, `open-uri` / `URI\.open\(`, `Faraday`, `HTTParty`, `RestClient` | allow-list |
| XXE | `Nokogiri::XML\(.*NOENT`, `REXML`, `LibXML` | Nokogiri defaults (no `NOENT`, `NONET` on) |
| TLS bypass | `VERIFY_NONE`, `verify_mode\s*=`, `ssl_verify.*false` | `VERIFY_PEER` |
| XSS | `html_safe`, `\braw\(`, `<%==`, `sanitize: false` | default ERB escaping; `sanitize` helper |
| Mass assignment | `params\.permit!`, `\.new\(params\[`, `update\(params\[` | strong parameters with an explicit list |

## PHP

| Check | Grep | Safe form |
|---|---|---|
| SQL injection | `mysqli_query\(`, `->query\(.*\$`, `->exec\(.*\$`, `DB::raw\(`, `whereRaw\(.*\$` | PDO prepared statements with bound parameters |
| Command injection | `\bexec\(`, `shell_exec\(`, `system\(`, `passthru\(`, `popen\(`, `proc_open\(`, backticks | `escapeshellarg` per argument; avoid the shell |
| Code injection | `\beval\(`, `assert\(` with a string, `create_function`, `preg_replace\(.*/e`, `call_user_func\(\s*\$_` | no dynamic code |
| File inclusion / traversal | `(include\|require)(_once)?\s*\(?\s*\$`, `file_get_contents\(\s*\$`, `fopen\(\s*\$`, `readfile\(`, `move_uploaded_file\(` | `realpath` then prefix check; fixed include map |
| Deserialization | `unserialize\(`, `phar://` in a path built from input | `json_decode`; `allowed_classes => false` |
| SSRF | `curl_setopt\(.*CURLOPT_URL`, `file_get_contents\(\s*\$` with a URL, Guzzle with input | allow-list; `CURLOPT_FOLLOWLOCATION` off; restrict `CURLOPT_PROTOCOLS` |
| XXE | `simplexml_load_`, `DOMDocument.*load`, `LIBXML_NOENT`, `libxml_disable_entity_loader\(false\)` | no `LIBXML_NOENT`; PHP 8 / libxml 2.9+ defaults |
| TLS bypass | `CURLOPT_SSL_VERIFYPEER.*(false\|0)`, `CURLOPT_SSL_VERIFYHOST.*0`, `verify_peer.*false` | leave on |
| XSS | `echo\s+\$_(GET\|POST\|REQUEST\|COOKIE)`, `\{!!`, `<\?=\s*\$` without `htmlspecialchars` | `htmlspecialchars(..., ENT_QUOTES)`; Blade `{{ }}` |
| Type juggling | `==` on tokens or hashes, `in_array\(` without strict, `strcmp\(` on input | `===`, `hash_equals` |

## Rust

Memory safety removes a class of bugs, not this one — the logic flaws below are the same in any language.

| Check | Grep | Safe form |
|---|---|---|
| SQL injection | `format!\(.*(SELECT\|INSERT\|UPDATE\|DELETE)`, `sqlx::query\(&` with a built string, `\.execute\(&format!` | `sqlx::query!` / bound parameters; Diesel's query builder |
| Command injection | `Command::new\(\s*"(sh\|bash\|cmd)"`, `\.arg\(format!` into a shell | `Command::new(prog).args([...])`, no shell |
| Path traversal | `File::open\(`, `fs::read`, `Path::join\(` / `\.join\(` (an absolute argument replaces the base), archive extraction | `canonicalize` then `starts_with(base)` |
| Deserialization | `bincode`, `serde_yaml`, `rmp_serde` on untrusted bytes without size limits; `#[serde(untagged)]` on input enums | size limits; `deny_unknown_fields` |
| SSRF | `reqwest::`, `hyper::Client`, `ureq::` | allow-list; `redirect::Policy::none()` |
| TLS bypass | `danger_accept_invalid_certs\(true\)`, `danger_accept_invalid_hostnames`, `dangerous\(\)` | default verifier |
| Unsafe | `unsafe\s*\{`, `transmute`, `from_raw_parts`, `get_unchecked`, `from_utf8_unchecked` | review each for a stated safety invariant |
| Panics as DoS | `\.unwrap\(\)` / `\.expect\(` / indexing on values derived from input in a request path | return an error |

## Shell, Dockerfiles and CI

These are in almost every repo and are easy to skip because they are not "the code".

| Check | Grep | What to verify |
|---|---|---|
| Shell injection | `eval\s`, unquoted `\$[A-Za-z_{]` in a command position, `curl .*\|\s*(ba)?sh`, `bash -c ".*\$` | variables quoted; no piping a download into a shell; arrays for argument lists |
| Dockerfile | `^ADD\s+https?://`, `curl .*\|\s*sh`, `^USER\s+root` as the last USER or no USER at all, `ARG\s+.*(TOKEN\|PASSWORD\|SECRET)`, `ENV\s+.*(TOKEN\|PASSWORD\|SECRET)`, `:latest` | pinned digests; a non-root user; build secrets via `--mount=type=secret`, not `ARG`/`ENV` |
| GitHub Actions | `pull_request_target`, `\$\{\{\s*github\.event\.(issue\|pull_request\|comment\|head_commit)\.` inside a `run:` block, `uses:\s*\S+@(main\|master\|v\d+)$`, `permissions:\s*write-all` | untrusted event text passed through `env:`, never interpolated into a script; third-party actions pinned to a commit SHA; least-privilege `permissions` |
| Other CI | secrets echoed to logs, `set -x` around a secret, tokens in a URL | masked variables; no tracing near secrets |
| IaC | `0\.0\.0\.0/0` on admin ports, `publicly_accessible\s*=\s*true`, `acl\s*=\s*"public-read"`, wildcard `"Action":\s*"\*"` / `"Resource":\s*"\*"` | scoped network rules and policies |

## Where untrusted input comes from

A sink matters only if input reaches it. When tracing a hit backwards, these are the sources to look for:

- **HTTP**: query string, path parameters, body, headers (including `Host`, `X-Forwarded-*`, `Referer`, `User-Agent`), cookies, uploaded files and their filenames.
- **Stored data that was once input**: database rows, cache entries, queue messages — second-order injection is the same bug with a delay.
- **Files and archives** the program reads: names inside a zip or tar, parsed documents, config a user can edit.
- **Environment and arguments** where a less-trusted party sets them: CI variables from a fork, CLI arguments in a setuid or service context.
- **Other services**: webhook payloads, responses from third-party APIs, anything deserialized from the network.

Trusted: constants, values from the program's own config that only operators control, and data already validated against a strict schema on this code path.
