---
name: jacoco
description: Check JaCoCo code coverage for a Maven/Java project against a coverage gate, then drill into per-module, per-class, and per-line gaps to target tests. Use when checking coverage, finding uncovered code, or planning tests to reach a coverage threshold.
argument-hint: "[module-or-class]"
---

## Check JaCoCo Code Coverage

> **Try it:** `/maven-quality:jacoco payment-service` — or say "what's our test coverage on the payment service?".

Run `verify` to generate coverage reports, then parse and display the results.
Defaults target a Maven/Java project with the JaCoCo plugin bound so that
`verify` produces `target/site/jacoco/jacoco.xml`.

### Coverage gate: **80%** line coverage (default)

Adjust `THRESHOLD` in the snippets below to match your project's gate.

### Adjusting for your project

- **Maven invocation**: examples use the wrapper `./mvnw`. If your environment has no wrapper, substitute your `mvn` binary, e.g. `bash "/path/to/mvn" verify -f pom.xml -q`.
- **Single module / non-modular project**: the report lives at `target/site/jacoco/jacoco.xml`. Set `modules = ['.']` and use `'.'/target/...` paths, or just drop the `module` prefix.
- **Multi-module project**: set the `modules` list to your module directory names, or pass one module as the argument to scope to it.
- `$ARGUMENTS` (when present) is treated as either a module name (Steps 1, 2, 5, 7) or a class source-file name (Step 4).

### Step 1: Generate coverage reports

**Specific module** (e.g. argument = `my-core`):

```bash
./mvnw verify -pl $ARGUMENTS -q
```

**All modules / whole project:**

```bash
./mvnw clean verify -q
```

### Step 2: Module-level summary (PASS/FAIL vs gate)

```python
python3 -c "
import xml.etree.ElementTree as ET

THRESHOLD = 80
# Adjust to your module directory names, or use ['.'] for a single-module project.
modules = ['module-a', 'module-b', 'module-c']
if '$ARGUMENTS':
    modules = ['$ARGUMENTS']

print(f'{\"Module\":<24} {\"Covered\":>8} {\"Total\":>8} {\"Coverage\":>10} {\"Status\":>8}')
print('-' * 62)
for module in modules:
    path = f'{module}/target/site/jacoco/jacoco.xml' if module != '.' else 'target/site/jacoco/jacoco.xml'
    try:
        root = ET.parse(path).getroot()
        for counter in root.findall('counter'):
            if counter.get('type') == 'LINE':
                missed = int(counter.get('missed'))
                covered = int(counter.get('covered'))
                total = missed + covered
                pct = covered / total * 100 if total > 0 else 0
                status = 'PASS' if pct >= THRESHOLD else 'FAIL'
                print(f'{module:<24} {covered:>8} {total:>8} {pct:>9.2f}% {status:>8}')
    except FileNotFoundError:
        print(f'{module:<24} {\"N/A\":>8} {\"N/A\":>8} {\"N/A\":>10} {\"MISSING\":>8}')
"
```

### Step 3: Class-level breakdown (lowest coverage first)

```python
python3 -c "
import xml.etree.ElementTree as ET

module = '$ARGUMENTS' if '$ARGUMENTS' else 'module-a'
path = f'{module}/target/site/jacoco/jacoco.xml' if module != '.' else 'target/site/jacoco/jacoco.xml'
root = ET.parse(path).getroot()
results = []
for pkg in root.findall('.//package'):
    for cls in pkg.findall('class'):
        for counter in cls.findall('counter'):
            if counter.get('type') == 'LINE':
                missed = int(counter.get('missed'))
                covered = int(counter.get('covered'))
                total = missed + covered
                if total > 0:
                    results.append((covered / total * 100, missed, covered, total, cls.get('name')))
results.sort()
print(f'{\"Coverage\":>10} {\"Missed\":>8} {\"Covered\":>8} {\"Total\":>8}  Class')
print('-' * 80)
for pct, missed, covered, total, name in results:
    print(f'{pct:>9.1f}% {missed:>8} {covered:>8} {total:>8}  {name}')
"
```

### Step 4: Uncovered lines in a specific class

Set `CLASS_NAME` (or pass the class source file as the argument) to find exact
uncovered line numbers for targeted test writing:

```python
python3 -c "
import xml.etree.ElementTree as ET

module = 'module-a'  # adjust to the module containing the class, or '.'
path = f'{module}/target/site/jacoco/jacoco.xml' if module != '.' else 'target/site/jacoco/jacoco.xml'
root = ET.parse(path).getroot()

CLASS_NAME = '$ARGUMENTS.java' if '$ARGUMENTS' else 'REPLACE_ME.java'

for pkg in root.findall('.//package'):
    for sf in pkg.findall('sourcefile'):
        if sf.get('name') == CLASS_NAME:
            uncovered = [int(line.get('nr')) for line in sf.findall('line') if int(line.get('mi', 0)) > 0]
            print(f'Uncovered lines in {CLASS_NAME}: {len(uncovered)} lines')
            for ln in uncovered:
                print(f'  Line {ln}')
"
```

### Step 5: Gap analysis (lines needed to reach the gate)

```python
python3 -c "
import xml.etree.ElementTree as ET
import math

THRESHOLD = 80
modules = ['module-a', 'module-b', 'module-c']
if '$ARGUMENTS':
    modules = ['$ARGUMENTS']

for module in modules:
    path = f'{module}/target/site/jacoco/jacoco.xml' if module != '.' else 'target/site/jacoco/jacoco.xml'
    try:
        root = ET.parse(path).getroot()
        for counter in root.findall('counter'):
            if counter.get('type') == 'LINE':
                missed = int(counter.get('missed'))
                covered = int(counter.get('covered'))
                total = missed + covered
                pct = covered / total * 100 if total > 0 else 0
                needed = math.ceil(THRESHOLD / 100 * total) - covered
                if needed > 0:
                    print(f'{module}: {pct:.2f}% — need {needed} more lines covered to reach {THRESHOLD}%')
                else:
                    print(f'{module}: {pct:.2f}% — ALREADY above {THRESHOLD}% (surplus: {-needed} lines)')
    except FileNotFoundError:
        print(f'{module}: No coverage report found')
"
```

### Step 6: Quick-win targets (classes with the smallest gaps)

```python
python3 -c "
import xml.etree.ElementTree as ET

module = '$ARGUMENTS' if '$ARGUMENTS' else 'module-a'
path = f'{module}/target/site/jacoco/jacoco.xml' if module != '.' else 'target/site/jacoco/jacoco.xml'
root = ET.parse(path).getroot()
results = []
for pkg in root.findall('.//package'):
    for cls in pkg.findall('class'):
        for counter in cls.findall('counter'):
            if counter.get('type') == 'LINE':
                missed = int(counter.get('missed'))
                covered = int(counter.get('covered'))
                total = missed + covered
                if total > 0 and missed > 0:
                    results.append((missed, covered, total, cls.get('name')))

results.sort(key=lambda x: x[0])  # fewest missed lines first
print(f'{\"Missed\":>8} {\"Covered\":>8} {\"Total\":>8} {\"Coverage\":>10}  Class')
print('-' * 80)
for missed, covered, total, name in results[:20]:
    print(f'{missed:>8} {covered:>8} {total:>8} {covered / total * 100:>9.1f}%  {name}')
"
```

### Step 7: Full summary (LINE, BRANCH, METHOD, CLASS)

```python
python3 -c "
import xml.etree.ElementTree as ET

modules = ['module-a', 'module-b', 'module-c']
if '$ARGUMENTS':
    modules = ['$ARGUMENTS']

for module in modules:
    path = f'{module}/target/site/jacoco/jacoco.xml' if module != '.' else 'target/site/jacoco/jacoco.xml'
    try:
        root = ET.parse(path).getroot()
        print(f'\n=== {module} ===')
        print(f'{\"Type\":<12} {\"Covered\":>8} {\"Missed\":>8} {\"Total\":>8} {\"Coverage\":>10}')
        print('-' * 50)
        for counter in root.findall('counter'):
            ctype = counter.get('type')
            missed = int(counter.get('missed'))
            covered = int(counter.get('covered'))
            total = missed + covered
            pct = covered / total * 100 if total > 0 else 0
            print(f'{ctype:<12} {covered:>8} {missed:>8} {total:>8} {pct:>9.2f}%')
    except FileNotFoundError:
        print(f'\n=== {module} === NO REPORT FOUND')
"
```

### Coverage improvement strategy

When coverage is below the gate:

1. Run **gap analysis** (Step 5) to see how many lines are needed.
2. Run **quick-win targets** (Step 6) to find classes with the fewest missed lines.
3. Run **uncovered lines** (Step 4) on those classes to find exact lines.
4. Write tests targeting those lines:
   - Use `@ParameterizedTest` to efficiently cover multiple code paths.
   - Use Mockito for external dependencies.
   - Focus on error/exception paths, which are often uncovered.
5. Re-run `verify` and the summary to confirm improvement.
