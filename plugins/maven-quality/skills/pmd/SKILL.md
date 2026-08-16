---
name: pmd
description: Set up, run, and triage PMD static analysis on a Maven/Java project — the ruleset, the plugin wiring, parsing the report by rule and priority, copy-paste detection, and how to suppress a finding at the right level. Use when the user says "run PMD", "PMD is failing", "fix the PMD violations", "add static analysis", "what's PMD complaining about", "suppress this rule", or when a Maven build fails at the validate phase with rule violations.
argument-hint: "[module-or-rule]"
---

## PMD static analysis for Maven/Java

> **Try it:** `/maven-quality:pmd payment-service` — or say "what's PMD complaining about?".

PMD finds *defects and design smells*, which is a different job from formatting.
Keep it distinct from the `codestyle` skill: spring-javaformat and Checkstyle
decide how code should look, PMD decides whether it is likely wrong.

Defaults below target a project with `maven-pmd-plugin` bound to `validate`,
producing `target/pmd.xml`. Adjust module names, phases, and paths to match.

### Adjusting for your project

- **Maven invocation**: examples use the wrapper `./mvnw`. Without one, substitute your `mvn` binary.
- **Multi-module**: scope with `-pl <module>`; each module writes its own `target/pmd.xml`.
- `$ARGUMENTS` (when present) is either a module name (Steps 1–3) or a rule name to explain and suppress (Step 6).

### Step 1: Run it

```bash
./mvnw pmd:check -q                    # whole project, fails on violation
./mvnw pmd:check -pl $ARGUMENTS -q     # one module
./mvnw pmd:pmd -q                      # report only, never fails the build
```

`pmd:check` re-runs the analysis, so there is no need to run `pmd:pmd` first.
When the build is already wired to `validate`, `./mvnw validate` does the same.

### Step 2: Read the report, not the console

The console output truncates and reorders. `target/pmd.xml` is the whole truth.

**The namespace is the trap.** The report is namespaced
(`http://pmd.sourceforge.net/report/2.0.0`), so a plain `findall("file")`
silently returns nothing and the report looks clean. Match on local names
instead — that also survives PMD changing the namespace between majors:

Stdlib `ElementTree` is deliberate — these skills add no dependencies. It refuses
external entities outright, so XXE does not apply; it *is* susceptible to entity-
expansion blowup, which is irrelevant for a file your own build just wrote. If you
ever point this at a report from an untrusted source, use `defusedxml` instead.

```python
import xml.etree.ElementTree as ET, sys, collections, pathlib

def local(el):                      # '{ns}violation' -> 'violation'
    return el.tag.rsplit('}', 1)[-1]

rows = []
for report in pathlib.Path('.').glob('**/target/pmd.xml'):
    for f in ET.parse(report).getroot():
        if local(f) != 'file':
            continue
        name = f.get('name', '').split('/src/main/java/')[-1]
        for v in f:
            if local(v) != 'violation':
                continue
            rows.append((int(v.get('priority', 5)), v.get('rule'),
                         v.get('ruleset'), name, v.get('beginline'),
                         ' '.join((v.text or '').split())))

if not rows:
    print('  no violations'); sys.exit()
print(f'  {len(rows)} violations\n')
for rule, n in collections.Counter(r[1] for r in rows).most_common():
    pri = min(r[0] for r in rows if r[1] == rule)
    print(f'  p{pri}  {n:>4}  {rule}')
```

### Step 3: Triage by priority, not by count

PMD priorities run **1 (highest) to 5 (lowest)**, and the count is a poor guide —
one p1 is worth more attention than fifty p4s.

| Priority | Treat as |
|---|---|
| **1–2** | Fix now. Real defect risk: resource leaks, broken equals/hashCode, thread-safety, swallowed exceptions. |
| **3** | Fix when touching the file. Design smells that are real but rarely urgent. |
| **4–5** | Decide once, then encode the decision in the ruleset. A p4 you keep re-reading is a p4 you should have excluded. |

The rule that matters most is the last one: **a finding you have consciously
decided to ignore should stop appearing.** A build that reports violations
nobody acts on trains everyone to ignore the build.

### Step 4: See the worst offenders

```python
# hottest files, then the exact lines
import collections
print('\n  files:')
for f, n in collections.Counter(r[3] for r in rows).most_common(10):
    print(f'    {n:>4}  {f}')
print('\n  p1-p2 detail:')
for pri, rule, rs, f, line, msg in sorted(r for r in rows if r[0] <= 2):
    print(f'    p{pri} {f}:{line}  {rule}\n         {msg}')
```

### Step 5: Copy-paste detection (CPD)

`maven-pmd-plugin` ships a duplicate-code detector that is off unless asked for,
and it catches a class of problem the rules cannot:

```bash
./mvnw pmd:cpd -q          # writes target/cpd.xml
./mvnw pmd:cpd-check -q    # fails the build on duplication
```

Parse `target/cpd.xml` the same way — `duplication` elements carry `lines` and
`tokens`, with a `file` child per occurrence. Start the gate loose
(`<minimumTokens>` around 100) and tighten it; starting strict on an existing
codebase produces a wall of findings and the gate gets removed.

### Step 6: Suppress at the right level

Three mechanisms, and picking the wrong one is how suppressions rot:

| Scope | Mechanism | Use when |
|---|---|---|
| Whole project | `<exclude name="RuleName"/>` in the ruleset | The rule does not fit this project's style or stack. **Always leave a comment saying why.** |
| One class or method | `@SuppressWarnings("PMD.RuleName")` | The rule is right in general, wrong here, and the reason is visible in the code. |
| One line | `// NOPMD - <reason>` | A genuine one-off. The reason is not optional; a bare `// NOPMD` is unreviewable. |

Prefer the narrowest scope that works. A project-wide exclusion added to silence
one class is how a ruleset quietly stops finding anything.

**Do not suppress to get green.** If a p1–p2 finding is wrong, it is worth the
minute to say why in the ruleset comment; if it is right, fix the code.

### The ruleset

PMD ships eight categories. Reference the categories you want wholesale, then
exclude what does not fit — that way a PMD upgrade brings new rules in
automatically instead of silently doing nothing.

```xml
<?xml version="1.0"?>
<ruleset name="project PMD rules"
         xmlns="http://pmd.sourceforge.net/ruleset/2.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://pmd.sourceforge.net/ruleset/2.0.0
                             https://pmd.sourceforge.io/ruleset_2_0_0.xsd">

  <description>PMD ruleset for &lt;project&gt;</description>

  <rule ref="category/java/bestpractices.xml">
    <exclude name="GuardLogStatement"/>   <!-- SLF4J parameterized logging already avoids the cost -->
    <exclude name="LooseCoupling"/>
    <exclude name="UnusedAssignment"/>    <!-- false positives on try/catch branch assignments -->
  </rule>

  <rule ref="category/java/errorprone.xml">
    <exclude name="AvoidDuplicateLiterals"/>
    <exclude name="MissingSerialVersionUID"/>
    <exclude name="InvalidLogMessageFormat"/>  <!-- false positives with SLF4J placeholders -->
  </rule>

  <rule ref="category/java/design.xml">
    <exclude name="LawOfDemeter"/>        <!-- flags idiomatic fluent/builder chains -->
    <exclude name="ImmutableField"/>      <!-- Spring injects into fields -->
    <exclude name="CyclomaticComplexity"/>
    <exclude name="CognitiveComplexity"/>
  </rule>

  <rule ref="category/java/multithreading.xml"/>
  <rule ref="category/java/performance.xml"/>
  <rule ref="category/java/codestyle.xml">
    <exclude name="OnlyOneReturn"/>
    <exclude name="LocalVariableCouldBeFinal"/>
    <exclude name="MethodArgumentCouldBeFinal"/>
    <exclude name="ShortVariable"/>
    <exclude name="LongVariable"/>
    <exclude name="ConfusingTernary"/>
    <exclude name="UselessParentheses"/>  <!-- the formatter owns parenthesis style -->
  </rule>

  <!-- Override a rule's properties rather than excluding it outright: -->
  <rule ref="category/java/codestyle.xml/ClassNamingConventions">
    <properties>
      <property name="utilityClassPattern" value="[A-Z][a-zA-Z0-9]*"/>
    </properties>
  </rule>
</ruleset>
```

Two categories are deliberately absent above: `documentation` (Javadoc rules —
usually Checkstyle's job, and enforcing both duplicates the noise) and `security`
(a small category whose good rules overlap dedicated scanners; the
`security-audit` skill covers that ground more thoroughly).

`LawOfDemeter` and `OnlyOneReturn` deserve their exclusions specifically: both
fire constantly on ordinary modern Java and finding a real defect through them is
rare, which is the definition of a rule that costs more than it returns.

### Wiring it into the build

```xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-pmd-plugin</artifactId>
  <version>${maven-pmd-plugin.version}</version>
  <configuration>
    <targetJdk>${java.version}</targetJdk>
    <rulesets><ruleset>pmd-ruleset.xml</ruleset></rulesets>
    <failOnViolation>true</failOnViolation>
    <printFailingErrors>true</printFailingErrors>   <!-- else the build says "1 violation" and nothing else -->
    <includeTests>false</includeTests>
    <linkXRef>false</linkXRef>                      <!-- avoids requiring the jxr report -->
  </configuration>
  <executions>
    <execution>
      <id>pmd-check</id>
      <phase>validate</phase>
      <goals><goal>check</goal></goals>
    </execution>
  </executions>
</plugin>
```

`printFailingErrors` is the one worth keeping: without it a failed build reports
a count and leaves you to go find the report yourself.

Binding to `validate` fails before compilation, which is fast but means a broken
build blocks every command. Bind to `verify` instead when the project is large
enough that the wait is felt.

### Adopting PMD on an existing codebase

A first run on a mature project produces hundreds of findings, and the usual
outcome is that the gate gets turned off. Avoid that:

1. Run `pmd:pmd` (report only, no failure) and count by priority.
2. Fix p1–p2. There are usually few, and they are usually real.
3. For everything else, decide per rule: exclude it in the ruleset with a comment, or keep it.
4. Only then set `failOnViolation` to `true`.

Alternatively set `<minimumPriority>2</minimumPriority>` to gate on p1–p2 first
and lower the number over time. Either way the gate should be green the day it is
switched on, or it will not survive.

### Related skills

- `codestyle` — spring-javaformat and Checkstyle. Formatting and naming, not defects.
- `precommit` — runs format, Checkstyle/PMD, and tests together before a commit.
- `jacoco` — coverage gate and gap analysis.
