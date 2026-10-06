# Make targets that report themselves.
#
#   make -f Makefile build PROGRESS_CLI="python3 <plugin>/scripts/progress.py"
#   make -f Makefile build          # no PROGRESS_CLI: plain commands
#
# RUN wraps one command as a timed job; from the second run the channel knows
# how long it takes and shows time left. For a tool that prints its own
# position (Maven, Gradle, cargo, pytest, docker …) pipe it through the tap
# instead — see taps.md.
PROGRESS_CLI ?=

ifeq ($(strip $(PROGRESS_CLI)),)
RUN = $(2)
else
RUN = $(PROGRESS_CLI) run --name '$(1)' -- $(2)
endif

.PHONY: build lint all
all: lint build

lint:
	@$(call RUN,example lint,sleep 0.1)

build:
	@$(call RUN,example build,sleep 0.2)
	@echo built
