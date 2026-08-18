# alexmskills — marketplace maintenance helpers
.DEFAULT_GOAL := help

.PHONY: help validate list bump graduate test-mindmap test-canvas test-ai test-linter test-evolve lint-skills install-help docs-build docs-rules library-refresh library-audit dev-link dev-unlink test-coach test-dashboard

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

validate: ## Validate the marketplace + all plugin manifests
	@bash scripts/validate-marketplace.sh

test-coach: ## Run the prompt-coach release test harness (run after each release)
	@python3 plugins/prompt-coach/scripts/test-harness.py

eval-coach: ## Score prompt-coach's rule fast-filter against the labeled golden set (add --gate in CI when corpus matures)
	@python3 plugins/prompt-coach/scripts/eval_coach.py

test-mindmap: ## Run the mindmap-prompt compiler harness (golden fixture + graph invariants)
	@python3 plugins/mindmap-prompt/scripts/test-harness.py

test-canvas: ## Playwright UI test for the mindmap canvas (optional; skips if playwright absent)
	@NODE_PATH="$${NODE_PATH:-$$HOME/.local/lib/playwright/node_modules}" \
		node plugins/mindmap-prompt/tests/pw-canvas.js

test-ai: ## Live smoke test of the mindmap ✦ expander (spends tokens; needs the claude CLI)
	@NODE_PATH="$${NODE_PATH:-$$HOME/.local/lib/playwright/node_modules}" \
		node plugins/mindmap-prompt/tests/pw-ai.js

test-evolve: ## Run the evolving-claude-md harness (coverage checks + hook contract)
	@python3 plugins/evolving-claude-md/skills/evolving-claude-md/test-harness.py

test-linter: ## Run the skill-linter harness (rules + false-positive guards)
	@python3 plugins/skill-linter/scripts/test-harness.py

lint-skills: ## Lint every SKILL.md in this marketplace
	@python3 plugins/skill-linter/scripts/lint_skills.py plugins

docs-rules: ## Regenerate the prompt-coach data-derived doc blocks (rules, catalog summary, config reference) from code
	@python3 plugins/prompt-coach/scripts/gen-rules-doc.py --inject

library-refresh: ## Refresh the vendored Claude Code Prompt Library snapshot (fetches live docs)
	@python3 plugins/prompt-coach/scripts/gen-prompt-library.py

library-audit: ## Calibration report — run the rule catalog over the gold prompt-library prompts
	@python3 plugins/prompt-coach/scripts/audit-library.py

test-dashboard: ## Playwright UI test for the coach web dashboard (optional; skips if playwright absent)
	@NODE_PATH="$${NODE_PATH:-$$HOME/.local/lib/playwright/node_modules}" \
		node plugins/prompt-coach/tests/pw-dashboard.js

list: ## List catalog: name, version, description
	@jq -r '.plugins[] | [.name, .version, .description] | @tsv' \
		.claude-plugin/marketplace.json | column -t -s "$$(printf '\t')"

bump: ## Bump a plugin version: make bump PLUGIN=dev-crew VERSION=1.1.0
	@test -n "$(PLUGIN)" || { echo "Usage: make bump PLUGIN=<name> VERSION=<x.y.z>"; exit 1; }
	@test -n "$(VERSION)" || { echo "Usage: make bump PLUGIN=<name> VERSION=<x.y.z>"; exit 1; }
	@f="plugins/$(PLUGIN)/.claude-plugin/plugin.json"; \
		tmp="$$(mktemp)"; \
		jq --arg v "$(VERSION)" '.version=$$v' "$$f" > "$$tmp" && mv "$$tmp" "$$f"; \
		mtmp="$$(mktemp)"; \
		jq --arg n "$(PLUGIN)" --arg v "$(VERSION)" \
			'(.plugins[] | select(.name==$$n) | .version) |= $$v' \
			.claude-plugin/marketplace.json > "$$mtmp" && mv "$$mtmp" .claude-plugin/marketplace.json; \
		echo "Bumped $(PLUGIN) -> $(VERSION) in plugin.json and marketplace.json"

graduate: ## Graduate a -beta plugin to stable: make graduate PLUGIN=prompt-coach
	@test -n "$(PLUGIN)" || { echo "Usage: make graduate PLUGIN=<name>-beta"; exit 1; }
	@echo "$(PLUGIN)" | grep -q -- '-beta$$' || { echo "Only -beta plugins can be graduated"; exit 1; }
	@new="$$(echo $(PLUGIN) | sed 's/-beta$$//')"; \
		test ! -d "plugins/$$new" || { echo "plugins/$$new already exists"; exit 1; }; \
		git mv "plugins/$(PLUGIN)" "plugins/$$new"; \
		jq --arg n "$$new" '.name=$$n' "plugins/$$new/.claude-plugin/plugin.json" > tmp && mv tmp "plugins/$$new/.claude-plugin/plugin.json"; \
		jq --arg from "$(PLUGIN)" --arg to "$$new" --arg src "./plugins/$$new" \
			'(.plugins[] | select(.name==$$from)) |= (.name=$$to | .source=$$src | del(.category) | .keywords -= ["beta"])' \
			.claude-plugin/marketplace.json > tmp && mv tmp .claude-plugin/marketplace.json; \
		echo "Graduated $(PLUGIN) -> $$new. Next: make bump PLUGIN=$$new VERSION=<x.y.z>"

dev-link: ## Symlink a plugin's cache dir to the live source (fast dev loop): make dev-link PLUGIN=<name>
	@test -n "$(PLUGIN)" || { echo "Usage: make dev-link PLUGIN=<name>"; exit 1; }
	@bash scripts/dev-link.sh "$(PLUGIN)"

dev-unlink: ## Remove the dev symlink and restore a real cache copy: make dev-unlink PLUGIN=<name>
	@test -n "$(PLUGIN)" || { echo "Usage: make dev-unlink PLUGIN=<name>"; exit 1; }
	@bash scripts/dev-link.sh --unlink "$(PLUGIN)"

install-help: ## Print local install/test commands for Claude Code
	@echo "Test locally (no install):  claude --plugin-dir ./plugins/<name>"
	@echo "Add this marketplace:       /plugin marketplace add $(PWD)"
	@echo "Install a plugin:           /plugin install <name>@alexmskills"
	@echo "Validate a plugin:          claude plugin validate   (run inside plugins/<name>)"
