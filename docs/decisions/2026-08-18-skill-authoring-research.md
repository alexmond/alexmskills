# Skill-authoring best practices — verified research record

Date: 2026-08-18 · Method: 6 parallel research agents across distinct source
categories, every lintable claim then adversarially verified (URL fetched, quote
confirmed, false-positive risk judged) by a second agent. 87 claims gathered,
41 survived with `keep=true`. This file is the durable record; the shipped rules
and their per-rule citations live in
`plugins/skill-linter/skills/skill-linter/references/rule-sources.md`.

Verification key: every claim below carries its exact source URL and the
verifier's note. Claims that did NOT survive are omitted here but retrievable
from the workflow journal.


## anthropic-docs (14 verified claims)

- **The frontmatter name field must be at most 64 characters, contain only lowercase letters, numbers, and hyphens, contain no XML tags, and must not contain the reserved words 'anthropic' or 'claude'.**
  - quote: “`name`: Maximum 64 characters, lowercase letters/numbers/hyphens only, no XML tags, no reserved words”
  - source: https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices
  - verifier: Page confirms the exact bullet list (Maximum 64 characters / lowercase-numbers-hyphens / no XML tags / reserved words: "anthropic", "claude"). Check is fully mechanical. One calibration: the reserved-word substring part should be warn-level in Claude Code-local mode — real working Code skills exist with 'claude' in the name (e.g. this repo's evolving-claude-md); it is a hard error only on the platform/claude.ai surface.
- **The frontmatter description must be non-empty, at most 1,024 characters, and contain no XML tags.**
  - quote: “`description`: Maximum 1,024 characters, non-empty, no XML tags”
  - source: https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices
  - verifier: Verbatim on the best-practices page ('description: Maximum 1,024 characters, non-empty, no XML tags'). Mechanical. Calibration: Claude Code itself tolerates longer descriptions (it truncates at 1,536 combined per code.claude.com), and long trigger-rich descriptions are common in Code marketplaces — enforce as fail in portable mode, warn in Code-only mode.
- **The description must always be written in third person because it is injected into the system prompt, and first/second-person phrasing can break skill discovery.**
  - quote: “**Always write in third person**. The description is injected into the system prompt, and inconsistent point-of-view can cause discovery problems.”
  - source: https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices
  - verifier: Quote verbatim, including the doc's Good/Avoid examples ('I can help you...', 'You can use this...'). The proposed regex is narrow, warn-level, and mirrors the doc's exact anti-examples; only residual FP is a quoted user trigger phrase containing 'I can/I will' — rare. Fine as a warning.
- **The description must state both what the skill does and when to use it, since it is the only text Claude matches requests against when deciding whether to trigger the skill.**
  - quote: “The `description` is what Claude matches your request against when determining whether to trigger the Skill, so it must say both what the Skill does and when to use it.”
  - source: https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview
  - verifier: Quote verbatim on the overview page — the claim itself is core, doc-backed guidance and must stay. But the proposed regex is too narrow: \bwhen\b does not match 'whenever', and good skills commonly phrase triggering as 'Use whenever...', 'Load when creating...', 'Use for any X task' — all would warn. Broaden the pattern set (whenever|use for|load when|trigger|use when|when the user) and keep it warn-level before shipping.
- **Keep the SKILL.md body under 500 lines; split content into separate files when approaching that limit.**
  - quote: “Keep SKILL.md body under 500 lines for optimal performance. If your content exceeds this, split it into separate files using the progressive disclosure patterns described earlier.”
  - source: https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices
  - verifier: Verbatim under 'Token budgets' on best-practices; also appears in the doc's own checklist ('SKILL.md body is under 500 lines'). Line-count after frontmatter is fully mechanical with essentially zero FP risk.
- **In Claude Code's skill listing the combined description plus when_to_use text is truncated at 1,536 characters, so the key use case must come first.**
  - quote: “Put the key use case first: the combined `description` and `when_to_use` text is truncated at 1,536 characters in the skill listing to reduce context usage.”
  - source: https://code.claude.com/docs/en/skills
  - verifier: Verbatim on code.claude.com/docs/en/skills; the page also confirms when_to_use 'counts toward the 1,536-character cap'. Mechanical length check; treat a missing when_to_use as empty. Warn-level is right since the tail is silently cut, not rejected.
- **Keep file references one level deep: every bundled reference file should be linked directly from SKILL.md, never only from another reference file.**
  - quote: “**Keep references one level deep from SKILL.md**. All reference files should link directly from SKILL.md to ensure Claude reads complete files when needed.”
  - source: https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices
  - verifier: Verbatim, with the doc's SKILL.md -> advanced.md -> details.md bad example. Link extraction is mechanical, but the implementation MUST skip fenced code blocks (the doc's own anti-pattern examples live in code fences, and skills quote markdown in examples) and resolve relative paths from the ref file's dir — otherwise it will FP on example snippets.
- **Reference files longer than 100 lines should include a table of contents at the top so partial reads still reveal the file's full scope.**
  - quote: “For reference files longer than 100 lines, include a table of contents at the top. This ensures Claude can see the full scope of available information even when previewing with partial reads.”
  - source: https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices
  - verifier: Verbatim, with a '## Contents' example. Mechanical and doc-accurate, but must be warn/advisory only: many otherwise-good skills ship >100-line refs without a labeled TOC, and a TOC without a 'contents' heading (bare bullet list) would be missed by the heading heuristic.
- **File paths in skills must always use forward slashes, even on Windows, because backslash paths break on Unix.**
  - quote: “Always use forward slashes in file paths, even on Windows: ... Unix-style paths work across all platforms, while Windows-style paths cause errors on Unix systems.”
  - source: https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices
  - verifier: Quote confirmed under 'Anti-patterns to avoid'. But the proposed regex [\w.]+\\[\w.]+ matches regex escape sequences (\d+\.\d+, \w+\.\w) and shell/LaTeX escapes, which are pervasive in real skill bodies (linters, prompt tooling) — it would flood. Restrict to markdown link targets plus strings with a drive-letter prefix ([A-Za-z]:\\) or 2+ backslash separators with no regex metacharacters, and skip code fences that contain regex syntax.
- **For skills meant to work on claude.ai or via the Skills API, frontmatter must be restricted to the Agent Skills spec's six fields (allowed-tools, compatibility, description, license, metadata, name); any other key is rejected with an unexpected-key error.**
  - quote: “Unexpected key(s) in SKILL.md frontmatter: argument-hint. Allowed properties are: allowed-tools, compatibility, description, license, metadata, name”
  - source: https://code.claude.com/docs/en/skills
  - verifier: The exact error message appears verbatim on code.claude.com, with surrounding text confirming upload/packaging 'fails with a hard error instead of ignoring the field' and that restricting to the six fields avoids it. Scoping the check to an explicit portable mode makes it FP-free by construction — Code-only keys are legitimate outside that mode.
- **Prefer gerund-form (verb+-ing) skill names and avoid vague or generic names like helper, utils, tools, documents, data, files.**
  - quote: “Consider using **gerund form** (verb + -ing) for Skill names, as this clearly describes the activity or capability the Skill provides.”
  - source: https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices
  - verifier: Gerund quote verbatim; the Avoid list on the same page confirms exactly: names helper/utils/tools, generic documents/data/files (plus anthropic-helper/claude-tools). Exact-match denylist is mechanical with near-zero FP; correctly leaves the gerund preference advisory.
- **Malformed frontmatter YAML makes Claude Code load the skill with empty metadata, so auto-triggering silently stops working even though manual /skill-name invocation still works.**
  - quote: “If the frontmatter YAML is malformed, Claude Code loads the skill body with empty metadata, so `/skill-name` still works but Claude has no `description` to match against.”
  - source: https://code.claude.com/docs/en/skills
  - verifier: Verbatim in the code.claude.com troubleshooting section (including the --debug tip). YAML-parse validation is fully mechanical. One nuance: the same page says a missing description falls back to the first paragraph, so a SKILL.md with no frontmatter at all is legal in Claude Code — only fail when a '---' block is present but unparseable; treat absent frontmatter as a separate portability finding.
- **The SKILL.md body (Level 2 instructions) is budgeted at under 5k tokens in Anthropic's progressive-disclosure model; each skill's always-loaded metadata costs roughly 100 tokens.**
  - quote: “| **Level 2: Instructions** | When Skill is triggered | Under 5k tokens | SKILL.md body with instructions and guidance |”
  - source: https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview
  - verifier: The overview's progressive-disclosure table confirms both verbatim: Level 2 'Under 5k tokens' and Level 1 '~100 tokens per Skill'. chars/4 is a rough estimator but fine at warn level; it usefully catches long-line files that pass the 500-line check.
- **The compatibility frontmatter field accepts a string of at most 500 characters.**
  - quote: “Accepts a string of up to 500 characters. Claude Code accepts the field but doesn't act on it.”
  - source: https://code.claude.com/docs/en/skills
  - verifier: Verbatim in the code.claude.com frontmatter table ('Accepts a string of up to 500 characters. Claude Code accepts the field but doesn't act on it.'). Type + length assertion on an optional key is fully mechanical, zero FP risk.

## anthropic-eng (9 verified claims)

- **The frontmatter `name` must be 1-64 chars of lowercase alphanumerics and hyphens, with no leading/trailing/consecutive hyphens, and must equal the skill's directory name.**
  - quote: “Must be 1-64 characters. May only contain unicode lowercase alphanumeric characters (a-z, 0-9) and hyphens (-). Must not start or end with a hyphen (-). Must not contain consecutive hyphens (--). Must match the parent directory name”
  - source: https://agentskills.io/specification
  - verifier: All five quoted fragments found verbatim on agentskills.io/specification. Regex + len + dirname equality is fully deterministic; zero FP risk on conforming skills.
- **The frontmatter `description` must be 1-1024 characters and should state both what the skill does and when to use it, with specific trigger keywords.**
  - quote: “Must be 1-1024 characters. Should describe both what the skill does and when to use it. Should include specific keywords that help agents identify relevant tasks”
  - source: https://agentskills.io/specification
  - verifier: Quote verbatim on spec. Presence/length check is mechanical. The when-clause regex as written flagged 3/26 good skills in this repo (all use 'whenever' or 'Use this to') — keep it warn-level and broaden to \bwhen(ever)?\b, 'use for', 'trigger[s]'.
- **All when-to-use information belongs in the description (the primary triggering mechanism), never only in the SKILL.md body.**
  - quote: “This is the primary triggering mechanism - include both what the skill does AND specific contexts for when to use it. All "when to use" info goes here, not in the body.”
  - source: https://github.com/anthropics/skills/blob/main/skills/skill-creator/SKILL.md
  - verifier: Quote verbatim at skill-creator SKILL.md line 67. The conjunction (no when-clause in description AND a 'When to use' body heading) makes FPs rare, but inherit the broadened when-regex from claim 2 or 'whenever'-style descriptions will misfire.
- **Keep SKILL.md under 500 lines; move detail to referenced files, adding a hierarchy layer with pointers when approaching the limit.**
  - quote: “Keep SKILL.md under 500 lines; if you're approaching this limit, add an additional layer of hierarchy along with clear pointers about where the model using the skill should go next to follow up.”
  - source: https://github.com/anthropics/skills/blob/main/skills/skill-creator/SKILL.md
  - verifier: Quote verbatim at skill-creator line 96; independently corroborated by the spec's 'Keep your main SKILL.md under 500 lines'. wc -l is fully mechanical; error>500 / warn~400 is sound.
- **The SKILL.md instruction body should stay under roughly 5000 tokens, since the whole file loads into context on activation.**
  - quote: “Instructions (< 5000 tokens recommended): The full SKILL.md body is loaded when the skill is activated”
  - source: https://agentskills.io/specification
  - verifier: Both quote fragments verbatim on spec ('Instructions (< 5000 tokens recommended)' + body-loaded-on-activation). chars/4 is a rough estimator — fine as a warn, never an error; note the spec itself says 'recommended'.
- **Large reference files (over 300 lines) should carry a table of contents so the model can navigate them without reading everything.**
  - quote: “For large reference files (>300 lines), include a table of contents”
  - source: https://github.com/anthropics/skills/blob/main/skills/skill-creator/SKILL.md
  - verifier: Quote verbatim at skill-creator line 98. TOC-signal heuristic (Contents heading OR >=3 anchor links in first ~50 lines) is mechanical; keep warn-level since valid TOCs can be formatted otherwise, and scan all skill-local .md >300 lines, not just references/.
- **File references must use relative paths from the skill root and stay one level deep from SKILL.md — no nested reference chains.**
  - quote: “When referencing other files in your skill, use relative paths from the skill root ... Keep file references one level deep from SKILL.md. Avoid deeply nested reference chains.”
  - source: https://agentskills.io/specification
  - verifier: Both spec sentences joined by the ellipsis found verbatim. Absolute-path and dead-link checks are precise (must exclude http(s):// and anchors); chain-depth>1 should be a warn, since a referenced .md linking onward can be legitimate.
- **The optional `compatibility` field is capped at 500 characters and should be omitted unless the skill has real environment requirements.**
  - quote: “Must be 1-500 characters if provided. Should only be included if your skill has specific environment requirements ... Most skills do not need the compatibility field.”
  - source: https://agentskills.io/specification
  - verifier: All three fragments verbatim on spec. Length bound is mechanical; 'most skills should omit' must stay an informational note, never a failure.
- **For every bundled script, the skill must make explicit whether Claude should execute it or read it as reference documentation.**
  - quote: “Code can serve as both executable tools and as documentation. It should be clear whether Claude should run scripts directly or read them into context as reference.”
  - source: https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills
  - verifier: Source reads 'Finally, code can serve...' — trivial drift. Claim slightly strengthens 'should be clear' to per-script 'must'; basename-mention check flagged 0/26 skills here. Downgrade to warn for helper modules imported by a mentioned entry script; run-vs-read intent stays judgment, as the proposal concedes.

## superpowers (6 verified claims)

- **Keep the description under 500 characters when possible; the frontmatter hard caps are 64 characters for name and 1024 for description.**
  - quote: “Keep under 500 characters if possible”
  - source: file:///home/alexm/.claude/plugins/cache/claude-plugins-official/superpowers/6.3.0/skills/writing-skills/SKILL.md (upstream: https://github.com/obra/superpowers/blob/main/skills/writing-skills/SKILL.md)
  - verifier: Exact quote at SKILL.md line 103. The 64/1024 hard caps are verbatim in the sibling anthropic-best-practices.md lines 149-150 and 1095 (SKILL.md itself says 'Max 1024 characters total' for the frontmatter). Pure length checks — fully mechanical, no FP risk on good skills.
- **Keep the SKILL.md body under 500 lines; split overflow into separate progressively-disclosed files.**
  - quote: “Keep SKILL.md body under 500 lines for optimal performance. If your content exceeds this, split it into separate files using the progressive disclosure patterns described earlier.”
  - source: file:///home/alexm/.claude/plugins/cache/claude-plugins-official/superpowers/6.3.0/skills/writing-skills/anthropic-best-practices.md (upstream: https://github.com/obra/superpowers/blob/main/skills/writing-skills/anthropic-best-practices.md)
  - verifier: Quote verbatim at anthropic-best-practices.md line 1099 (also line 241, checklist line 1109); this is official Anthropic guidance. Only 2 of 12 superpowers skills trip it, so warn-level is calibrated. Count body lines after the closing '---' delimiter.
- **Cross-reference other skills by bare name with an explicit requirement marker, never with @-links, because @ syntax force-loads the file immediately.**
  - quote: “**Why no @ links:** `@` syntax force-loads files immediately, consuming 200k+ context before you need them.”
  - source: file:///home/alexm/.claude/plugins/cache/claude-plugins-official/superpowers/6.3.0/skills/writing-skills/SKILL.md (upstream: https://github.com/obra/superpowers/blob/main/skills/writing-skills/SKILL.md)
  - verifier: Quote verbatim at SKILL.md line 288; requirement-marker guidance at lines 279-287. Keep ONLY the skills/-anchored regex (/@\S*skills\//): the broader 'any @-prefixed relative path' clause would FP on Vite '@/src' alias imports and npm scoped packages (@anthropic-ai/...) inside code blocks of good skills like vite/vue.
- **All bundled reference files must be linked directly from SKILL.md — one level deep — because nested references get partially read (head -100) and lose information.**
  - quote: “**Keep references one level deep from SKILL.md**. All reference files should link directly from SKILL.md to ensure agents read complete files when needed.”
  - source: file:///home/alexm/.claude/plugins/cache/claude-plugins-official/superpowers/6.3.0/skills/writing-skills/anthropic-best-practices.md (upstream: https://github.com/obra/superpowers/blob/main/skills/writing-skills/anthropic-best-practices.md)
  - verifier: Quote verbatim at anthropic-best-practices.md line 357; the head -100 rationale is verbatim at line 355. Link-graph analysis is mechanical. To avoid FPs, scope to .md files and exclude examples/, fixtures/, and test dirs (superpowers' own writing-skills bundles an examples/ dir not linked as reference).
- **Reference files longer than 100 lines need a table of contents at the top so partial reads still reveal the file's full scope.**
  - quote: “For reference files longer than 100 lines, include a table of contents at the top. This ensures agents can see the full scope of available information even when previewing with partial reads.”
  - source: file:///home/alexm/.claude/plugins/cache/claude-plugins-official/superpowers/6.3.0/skills/writing-skills/anthropic-best-practices.md (upstream: https://github.com/obra/superpowers/blob/main/skills/writing-skills/anthropic-best-practices.md)
  - verifier: Quote verbatim at anthropic-best-practices.md line 385, official Anthropic guidance. Keep at warn/advisory: the >100-line trigger is exact; TOC detection should accept any of — a 'Contents'-style heading, intra-file #anchor links, or a top-of-file bullet list of section names — within the first ~30 lines, else FPs on differently-structured but fine files.
- **All installed skill and command descriptions share one silent system-prompt budget of 15,000 characters (~4000 tokens); skills past the cutoff become invisible to Claude with no warning, so verbose descriptions can disable other skills.**
  - quote: “The limit for skill and command descriptions defaults to 15,000 characters (or around 4000 tokens). ... Since there's no warning when you go over, you might find yourself with unusable skills.”
  - source: https://blog.fsck.com/2025/12/17/claude-code-skills-not-triggering/
  - verifier: Page live (Jesse Vincent, blog.fsck.com); both sentences verified verbatim: 'the limit for skill and command descriptions defaults to 15,000 characters (or around 4000 tokens)' and 'since there's no warning when you go over, you might find yourself with unusable skills'. Collection-level sum with a 12k warn is mechanical and can't FP on individual skills. Caveats for the rule text: limit is 'as of Claude Code 2.0.70' and is a default (configurable), and the real budget spans ALL installed plugins, so the marketplace sum is a lower bound.

## practitioners (6 verified claims)

- **Write the description as the literal phrases a user would type to trigger the skill, not an abstract summary of what it manages — abstract descriptions never fire.**
  - quote: “My first version of a skill had the description 'Manages my project operations.' Claude never fired it...I rewrote it to list the literal phrases I'd type ('set up the project here', 'audit this', 'rebuild the index') and it fired on the first matching request.”
  - source: https://codemeetai.substack.com/p/how-to-create-a-claude-code-skill
  - verifier: Quote verbatim on the live codemeetai post (incl. 'Not once.'). Check is a pure regex on the frontmatter description. Broaden the when-clause markers beyond 'Use when'/'when the user' (add 'whenever', 'use this when', 'should be used when') or good skills phrased that way without quoted phrases get flagged.
- **The description should answer 'when should Claude use this skill', and de-emphasize 'what it does' — a Claude that thinks it already knows what the skill does will skip loading it and wing it.**
  - quote: “Showing only 'When should Claude use this skill?' leads to better compliance. When Claude thinks it knows what a skill does, it's more likely to believe it's using the skill and just wing it.”
  - source: https://blog.fsck.com/2025/10/16/skills-for-claude/
  - verifier: Jesse Vincent's post, quote near-verbatim ('In my testing, I've found that showing only...' + trailing 'even if it hasn't read it yet'). The regex (Use when|when the user|whenever) is mechanical; it only checks presence of a trigger condition, not absence of a what-clause — acceptable partial enforcement, low FP rate on well-written skills.
- **Auxiliary-folder names carry meaning to Claude: references/ holds read-only context docs, templates/ holds scaffolds to be copied with placeholders, and confusing the two produces wrong behavior in both directions.**
  - quote: “Get it backwards and Claude will either write a reference doc into your project (wrong) or treat a scaffold as read-only and never produce output (also wrong).”
  - source: https://codemeetai.substack.com/p/how-to-create-a-claude-code-skill
  - verifier: Quote matches (source says 'never produce the output'). But the proposed check doesn't test the claim: references-vs-templates confusion is semantic, not structural. The root-placement half flags a common good layout — a single helper script beside SKILL.md (e.g. evolving-claude-md's lint-claude-md.py at skill root). Only the broken-link half is safely mechanical; keep the claim as guidance, ship at most the dead-link check.
- **Frontmatter metadata is the only always-loaded part and costs only a few dozen tokens per skill — keep name+description tight so many skills can coexist cheaply.**
  - quote: “each skill only takes up a few dozen extra tokens, with the full details only loaded in should the user request a task that the skill can help solve.”
  - source: https://simonwillison.net/2025/Oct/16/claude-skills/
  - verifier: Verbatim on Simon Willison's post. Length measurement is fully mechanical. Set the budget at the 1024-char spec limit (warn near it), not 500: a 500-char warn contradicts claim 1's advice to enumerate literal trigger phrases and would flag many deliberately trigger-rich, well-regarded descriptions.
- **State quality rules as measurable numeric constraints Claude can enforce (e.g. a 30-line function limit), not vague adjectives.**
  - quote: “extract functions longer than 30 lines into smaller units”
  - source: https://self.md/guides/writing-skills-tutorial/
  - verifier: Context verified: the bullet is a GOOD example in self.md's 'be specific, not aspirational' section ('the first is a wish. the second is a checklist Claude can actually follow'), so the claim is genuinely supported. The check is not mechanical: 'concrete artifact name' is undefinable by regex, imperative-line detection is fuzzy, and 'properly'/'as needed'/'good' appear constantly in legitimate skill prose — would flood FPs. Keep as guidance only.
- **Keep the skills directory under version control (or symlink it from a controlled repo), otherwise each machine silently runs a divergent skill version.**
  - quote: “If `~/.claude/skills/` isn't version-controlled, every machine you work on runs a slightly different version.”
  - source: https://codemeetai.substack.com/p/how-to-create-a-claude-code-skill
  - verifier: Quote verbatim (source adds ', and you stop trusting them'). Resolving the symlink target and walking up for .git is fully mechanical. Exclude marketplace-managed paths (~/.claude/plugins/cache/...) — those aren't git worktrees locally but are versioned upstream, and flagging them would be systematic FPs.

## cross-vendor (6 verified claims)

- **Cap an instruction file at roughly 500 lines and split anything larger into multiple composable units (corroborates Claude's own SKILL.md size guidance).**
  - quote: “Keep rules under 500 lines. Split large rules into multiple, composable rules”
  - source: https://cursor.com/docs/context/rules
  - verifier: Live at cursor.com/docs/context/rules. Quote appears as two adjacent bullets: 'Keep rules under 500 lines' / 'Split large rules into multiple, composable rules'. Line-count check is fully mechanical; a 500-line warn will not flag well-written skills (Anthropic's own guidance sets the same bar).
- **Copilot sets an upper bound of about 1,000 lines per instruction file, beyond which instructions start being overlooked — a second vendor datapoint for a hard size ceiling.**
  - quote: “Limit any single instruction file to a maximum of about 1,000 lines. ... Very long instruction files may result in some instructions being overlooked.”
  - source: https://docs.github.com/en/copilot/tutorials/customize-code-review
  - verifier: Both sentences verbatim on the page ('Limit any single instruction file to a maximum of about 1,000 lines. Beyond this, the quality of responses may deteriorate.' and 'Very long instruction files may result in some instructions being overlooked.'). Mechanical, near-zero FP. Caveat: source hedges with 'about' and 'may', so hard-fail at exactly 1,000 is a policy choice stricter than the source — acceptable as a linter ceiling.
- **When the main instruction file grows too large, keep it concise and push detail into referenced task-specific markdown files (cross-vendor corroboration of progressive disclosure).**
  - quote: “If AGENTS.md starts getting too large, keep the main file concise and reference task-specific markdown files”
  - source: https://developers.openai.com/codex/learn/best-practices
  - verifier: URL 301s to learn.chatgpt.com/guides/best-practices but is the official OpenAI Codex best-practices page (og:description 'Getting started with Codex and proven practices'). Exact sentence found: 'If AGENTS.md starts getting too large, keep the main file concise and reference task-specific markdown files...'. Check is mechanical (size threshold AND zero relative .md links -> flag; resolve each relative link). Only fires on large, reference-free skills, so FP risk on good skills is low; the broken-link half is exact.
- **Structure instructions as distinct headings plus bullet points with short imperative directives, not long narrative paragraphs.**
  - quote: “Copilot benefits from well-structured instructions with: Distinct headings that separate different topics. Bullet points for easy scanning and reference. Short, imperative directives rather than long narrative paragraphs.”
  - source: https://docs.github.com/en/copilot/tutorials/customize-code-review
  - verifier: Quote confirmed verbatim (headings/bullets/imperative-directives bullet list). Primary check (>=1 heading, >=1 list) is mechanical and passes any well-written skill. The optional 8-consecutive-non-list-lines paragraph heuristic MUST exclude fenced code blocks and tables or it will false-positive; implement it as a soft warn only.
- **Vague meta-instructions like 'Be more accurate' or 'Don't miss any issues' add noise without changing behavior and should be removed.**
  - quote: “"Vague quality improvements" like "Be more accurate" and "Don't miss any issues" add noise without improving effectiveness.”
  - source: https://docs.github.com/en/copilot/tutorials/customize-code-review
  - verifier: Source confirmed: 'Vague quality improvements' section lists 'Be more accurate' and 'Don't miss any issues', with 'add noise without improving Copilot's effectiveness'; the exact_quote is a trivially close paraphrase. But the proposed stoplist over-reaches: bare substrings 'be accurate'/'be careful'/'be thorough' match legitimate specific directives ('be careful to escape quotes', 'output must be accurate to 2 decimals') that good skills use routinely — as written it would flood FPs. Keep the claim, but narrow the check to standalone vague exhortations (whole-sentence/whole-bullet matches like 'Be more accurate.', "Don't miss any issues.", 'Do your best.') before shipping it as a lint rule.
- **Scope instructions to when they apply (Copilot uses applyTo glob frontmatter; the SKILL.md analogue is a description that states its trigger conditions).**
  - quote: “At the start of the file, create a frontmatter block containing the applyTo keyword. Use glob syntax to specify what files or directories the instructions apply to.”
  - source: https://docs.github.com/en/copilot/customizing-copilot/adding-repository-custom-instructions-for-github-copilot
  - verifier: Quote confirmed verbatim ('At the start of the file, create a frontmatter block containing the applyTo keyword. Use glob syntax to specify what files or directories the instructions apply to.'). Caveat: the citation is analogical — applyTo is mechanical file-glob scoping, not a natural-language trigger description — so this is weak corroboration; the direct authority for the check is Anthropic's own skill-description guidance. The check itself is mechanical and low-FP provided the cue list is broad (use when / use whenever / use this / when the user / trigger / use proactively), since virtually all well-written descriptions contain such a cue.

## What became of it

- 14 new shipped rules + 1 collection-level check in skill-linter 0.3.0, each
  cited in rule-sources.md.
- One new documented conflict between official sources (TOC at 100 vs 300
  lines) — resolved to the looser bound with reasoning.
- Three findings deliberately NOT enforced (reserved words, gerund naming,
  version-control placement), recorded with reasons so they are not re-added
  from first principles.
- Calibration: +20 warnings across 69 external skills, all hand-verified true;
  0 new findings on this repo. Two FP classes were caught and fixed during
  calibration (angle-bracket CLI placeholders read as XML; Claude Code's
  documented frontmatter extras read as non-portable).

