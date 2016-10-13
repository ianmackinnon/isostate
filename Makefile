SHELL := /bin/bash
.PHONY : all clean package install install_config install_sources uninstall test

PYTHON = python3
CONFIG_PATH = /etc/isostate
SOURCES_PATH := $(CONFIG_PATH)/sources
NAME = isostate
TMP = /tmp/$(name).tmp
VERSION = 0.2dev
DIST := dist/$(NAME)-$(VERSION).tar.gz


all :
clean :


isostate.csv : sources/*.csv
	cat $^ > $(TMP)
	mv $(TMP) $@


package : isostate.py setup.py
	$(PYTHON) setup.py sdist

$(DIST) : package


$(CONFIG_PATH)/isostate.csv : isostate.csv
	mkdir -p $(CONFIG_PATH)
	cp isostate.csv $(CONFIG_PATH)
	chmod -R a+w $(CONFIG_PATH)

install_config : $(CONFIG_PATH)/isostate.csv

install_sources :
	rsync -av sources/1* $(SOURCES_PATH)

install : install_config install_sources
	cp isostate.py /usr/local/bin/isostate
	$(PYTHON) setup.py install

uninstall :
	rm -f /usr/local/bin/isostate
	yes | sudo pip uninstall $(NAME)

purge : uninstall
	rm -rf $(CONFIG_PATH)
