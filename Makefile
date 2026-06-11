# alexmskills — marketplace maintenance helpers
.DEFAULT_GOAL := help

.PHONY: help validate list bump new-beta promote install-help docs-build

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

validate: ## Validate every channel (stable + beta) + all plugin manifests
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

new-beta: ## Scaffold a beta-channel plugin: make new-beta NAME=my-skill
	@test -n "$(NAME)" || { echo "Usage: make new-beta NAME=<name>"; exit 1; }
	@bash scripts/new-beta-plugin.sh "$(NAME)"

promote: ## Promote a beta plugin to stable: make promote PLUGIN=my-skill
	@test -n "$(PLUGIN)" || { echo "Usage: make promote PLUGIN=<name>"; exit 1; }
	@bash scripts/promote-plugin.sh "$(PLUGIN)"

install-help: ## Print local install/test commands for Claude Code
	@echo "Test locally (no install):  claude --plugin-dir ./plugins/<name>"
	@echo "Add this marketplace:       /plugin marketplace add $(PWD)"
	@echo "Install a plugin:           /plugin install <name>@alexmskills"
	@echo "Validate a plugin:          claude plugin validate   (run inside plugins/<name>)"
