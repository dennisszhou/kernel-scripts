UV ?= uv

.PHONY: install

install:
	$(UV) tool install --force -e .
