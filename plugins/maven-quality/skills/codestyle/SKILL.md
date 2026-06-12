---
name: codestyle
description: Coding standards, formatting, and static-analysis conventions for Maven/Java projects using spring-javaformat, Checkstyle, and PMD. Use when checking or fixing code-style violations, or when asking what the project's formatting and naming rules are.
---

## Maven/Java Coding Standards

> **Try it:** `/maven-quality:codestyle` — or say "fix the code-style violations in this module".

These are sensible defaults for a Maven/Java project that uses
[spring-javaformat](https://github.com/spring-io/spring-javaformat),
Checkstyle, and PMD. Adjust thresholds, plugin versions, and module/path
names to match your project.

### Tooling (common case)

- **Formatter**: `io.spring.javaformat:spring-javaformat-maven-plugin` (tab indentation) — run `spring-javaformat:apply` before committing.
- **Checkstyle**: `maven-checkstyle-plugin` with `io.spring.javaformat:spring-javaformat-checkstyle` (`SpringChecks`) plus custom suppressions.
- **PMD**: `maven-pmd-plugin` with a custom ruleset.
- **Config files** (project root by default): `checkstyle-suppressions.xml`, `pmd-ruleset.xml`. Adjust paths if your project keeps them elsewhere.
- Violations typically **fail the build** at the `validate` phase. Adjust the bound phase if your `pom.xml` differs.

### Formatting rules enforced by spring-javaformat

- **Indentation**: Tabs.
- **Braces required**: All `if`, `else`, `for`, `while`, `do` use `{}` even for single-line bodies.
- **Lambda parentheses**: Single-parameter lambdas have parentheses: `(x) ->` not `x ->`.
- **Lambda blocks**: Prefer expression body: `(x) -> x.toString()` not `(x) -> { return x.toString(); }`.
- **Catch variables**: Use `ex` not single-letter `e`: `catch (Exception ex)`.
- **Ternary parentheses**: Wrap the condition: `(a != null) ? a : b`.
- **No star imports**: Explicit imports only, never `import java.util.*`.
- **Newline at EOF**: Files end with a trailing newline.

### Common Checkstyle suppressions

Default suppressions kept in `checkstyle-suppressions.xml`. Add or remove to taste:

- `SpringHeaderCheck` — no license header requirement.
- `JavadocPackage`, `JavadocType`, `JavadocMethod`, `JavadocVariable`, `MissingJavadocType`, `MissingJavadocMethod`, `SpringJavadoc` — Javadoc not enforced.
- `RegexpSinglelineJava` — no per-line regex restrictions.
- `SpringImportOrder` — import ordering not enforced.
- `RequireThis` — `this.` prefix not required.
- `SpringTestFileName` — flexible test file naming.

### Common PMD exclusions

Patterns considered acceptable, excluded in `pmd-ruleset.xml`. Tighten for stricter projects:

- **Best Practices**: `GuardLogStatement`, `LiteralsFirstInComparisons`, `UnusedAssignment`, `DoubleBraceInitialization`, `NonExhaustiveSwitch`, `RedundantFieldInitializer`
- **Code Style**: `LocalVariableNamingConventions`, `PrematureDeclaration`, `ConfusingTernary`, `UseLocaleWithCaseConversions`, `UseExplicitTypes`, `FieldNamingConventions`
- **Design**: `CognitiveComplexity`, `NcssCount`, `SimplifyConditional`, `CollapsibleIfStatements`, `GodClass`, `DataClass`, `TooManyFields`
- **Error Prone**: `ReturnEmptyCollectionRatherThanNull`, `AvoidDuplicateLiterals`, `NullAssignment`

### Naming

- Classes: `PascalCase`
- Methods / variables: `camelCase`
- Constants: `UPPER_SNAKE_CASE`

### Lombok (if used)

- `@Getter`/`@Setter` for fields
- `@Data` for POJOs/DTOs
- `@Builder` with `.toBuilder()` for immutable construction
- `@Slf4j` for logging
- `@NoArgsConstructor`, `@AllArgsConstructor` as needed

### Testing

- JUnit 5 with `Assertions`.
- Use `@ParameterizedTest` to avoid duplication.
- JaCoCo enforces a minimum line-coverage gate (default **80%** — see the `jacoco` skill; adjust per project).

### Workflow: check and fix violations

**1. Auto-format first** — fixes most style issues automatically:

```bash
./mvnw spring-javaformat:apply
```

**2. Check remaining violations:**

```bash
./mvnw validate 2>&1 | grep -E "violations|ERROR.*\.java|PMD Failure"
```

**3. Fix remaining violations manually:**

| Violation | Fix |
|-----------|-----|
| `SpringCatch` | Rename `catch (Exception e)` to `catch (Exception ex)` |
| `NeedBraces` | Add `{ }` to single-line `if`/`for`/`while` |
| `SpringLambda` parens | Wrap single lambda param: `x ->` becomes `(x) ->` |
| `SpringLambda` block | Convert `x -> { return expr; }` to `x -> expr` |
| `SpringTernary` | Wrap condition in parens: `(cond) ? a : b` |
| `AvoidStarImport` | Replace `import pkg.*` with specific imports |
| `SpringHideUtilityClassConstructor` | Add private constructor + `final` class |
| `AnnotationUseStyle` trailing comma | Remove `,` before `})` in annotations |
| `AppendCharacterWithChar` | Use `.append('x')` not `.append("x")` for single chars |
| `MissingOverride` | Add `@Override` on interface/superclass implementations |

**4. Re-format and validate until clean:**

```bash
./mvnw spring-javaformat:apply && ./mvnw validate
```

### Notes on invocation

- Examples use the Maven wrapper `./mvnw`. If your environment has no wrapper, substitute your `mvn` binary (e.g. `bash "/path/to/mvn" ...`).
- For multi-module builds, scope checks with `-pl <module>` (e.g. the module that actually holds source and the quality plugins).
