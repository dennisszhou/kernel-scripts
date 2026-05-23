UV ?= uv
UV_TOOL_BIN_DIR ?= $(CURDIR)/bin

.PHONY: install

install:
	mkdir -p "$(UV_TOOL_BIN_DIR)"
	XDG_BIN_HOME="$(UV_TOOL_BIN_DIR)" $(UV) tool install --force -e .
