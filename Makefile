# Usage: make release              # patch release
#        make release BUMP=minor   # minor release
#        make release BUMP=major   # major release
BUMP ?= patch
RELEASE_BRANCH ?= main

.PHONY: release

release:
	@RELEASE_BRANCH="$(RELEASE_BRANCH)" ./scripts/release.sh "$(BUMP)"
