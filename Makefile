# alexmskills — marketplace maintenance helpers
.DEFAULT_GOAL := help

.PHONY: help validate list bump graduate install-help docs-build dev-link dev-unlink

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

validate: ## Validate the marketplace + all plugin manifests
	@bash scripts/validate-marketplace.sh

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

graduate: ## Graduate a -beta plugin to stable: make graduate PLUGIN=prompt-coach-beta
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
