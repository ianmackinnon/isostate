SHELL := /bin/bash
NAME := isostate
VERSION := $(shell cat VERSION)
PYTHON := python3.12
TAR := dist/isostate-$(VERSION).tar.gz
WHL := dist/isostate-$(VERSION)-py3-none-any.whl
SUB := # eg. `[test]`


.PHONY : build test


all :

clean : clean-packages clean-test clean-python-cache


tox :
	.venv/bin/tox

tox-latest :
	.venv/bin/tox -e py39

build : $(WHL) $(TAR)

$(WHL) $(TAR) : 
	rm -rf dist
	python3 -m build
	unzip -l dist/$(NAME)-*.whl
	tar --list -f dist/$(NAME)-*.tar.gz

clean-packages :
	rm -rf .venv build dist *.egg-info

clean-test :
	rm -rf .pytest_cache .tox

clean-python-cache :
	find . -name __pycache__ -exec rm -rf {} +

install-virtualenv-dir :
	rm -rf .venv
	virtualenv --python $(PYTHON) .venv
	.venv/bin/pip install .$(SUB)
	find .venv | grep iso
	.venv/bin/isostate -l

install-virtualenv-tar : $(TAR)
	rm -rf .venv
	virtualenv --python $(PYTHON) .venv
	.venv/bin/pip install '$(TAR)$(SUB)'
	find .venv | grep iso
	.venv/bin/isostate -l

install-virtualenv-whl : $(WHL)
	rm -rf .venv
	virtualenv --python $(PYTHON) .venv
	.venv/bin/pip install '$(WHL)$(SUB)'
	find .venv | grep iso
	.venv/bin/isostate -l

install-virtualenv-test :
	rm -rf .venv
	virtualenv --python $(PYTHON) .venv
	.venv/bin/pip install -e .[test]

test :
	.venv/bin/pytest

tag :
	git tag -a v$(VERSION) -m v$(VERSION)
