#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import sys
import csv
import logging

from optparse import OptionParser
from collections import defaultdict



LOG = logging.getLogger('isostate')

CONFIG_PATH = "/etc/isostate"

ISOSTATE_CSV = "isostate.csv"
SOURCES_PATH = "sources"

DEFAULT_LANG = "en"
DEFAULT_NAME = "short"



class LookupNotFoundException(Exception):
    pass

class NameNotFoundException(Exception):
    pass



def codes(name=DEFAULT_NAME, lang=DEFAULT_LANG, source=None):
    code_dict = {}
    reader = Iso.source_iter(name, lang, source)
    for row in reader:
        if not len(row):
            continue
        iso2, _features, lang, name = row
        code_dict[iso2] = name
    return code_dict



class Iso(object):
    def __init__(self, source="text", cache=None):
        self._source = None
        self._cache_path = None
        self._lookup = {}

        if cache:
            self._cache_path = cache

        self.set_source(source)


    def set_source(self, source="text"):
        data = load_data(self._cache_path)

        assert source == "text"

        self._source = SourceText(data, sub=False)


    @staticmethod
    def key(name=DEFAULT_NAME, lang=DEFAULT_LANG):
        return "%s.%s" % (name, lang)


    @classmethod
    def source_iter(cls, name=DEFAULT_NAME, lang=DEFAULT_LANG, source=None):
        key = cls.key(name, lang)
        if source is None:
            source = "1.%s.csv" % key
            path = os.path.join(CONFIG_PATH, SOURCES_PATH, source)
            if not os.path.exists(path):
                path = os.path.join(SOURCES_PATH, source)
        else:
            path = source

        try:
            csv_data = open(path, "r", encoding="utf-8")
        except Exception as e:
            LOG.error(
                "Could not open file '%s' for name '%s' and language '%s'.",
                path, name, lang)
            raise e

        reader = csv.reader(csv_data, delimiter=';')
        return reader


    def add_lookup(self, name=DEFAULT_NAME, lang=DEFAULT_LANG, source=None):
        key = self.key(name, lang)
        reader = self.source_iter(name, lang, source)
        for row in reader:
            if not len(row):
                continue
            iso2, _features, lang, name = row
            if not key in self._lookup:
                self._lookup[key] = {}
            self._lookup[key][iso2] = name


    def name(self, iso2, name=DEFAULT_NAME, lang=DEFAULT_LANG):
        key = self.key(name, lang)

        if not key in self._lookup:
            raise LookupNotFoundException("No lookup found with key '%s'." % key)

        if not iso2 in self._lookup[key]:
            raise NameNotFoundException(
                "No name found for code '%s' in lookup '%s'." % (iso2, key))

        return self._lookup[key][iso2]


    def iso2(self, text, search=True, accept_sub=False):
        search_text = clean_text(text)

        assert self._source

        iso2, sub = self._source.match(search_text)

        if search and not iso2:
            iso2, sub = self._source.search(search_text, insert=self.insert)

        if iso2 and sub and not accept_sub:
            iso2 = None

        if iso2 == "  ":
            iso2 = None

        return iso2


    def insert(self, iso2, sub, lang, name):
        if self._cache_path:
            with open(self._cache_path, "a", encoding="utf-8") as fp:
                fp.write("%2s; %s; %2s; %s\n" % (
                    iso2 or "  ",
                    sub and ">" or "",
                    lang,
                    name,
                ))
        data = load_data(self._cache_path)
        self._source.reload(data)



class SourceText(object):
    def __init__(self, data, lang=DEFAULT_LANG, sub=False, size=(3, 5, 7)):
        self.lang = lang
        self.sub = sub
        self.size = size

        self.reload(data)


    def reload(self, data):
        self.data = data
        self.data = [row for row in self.data if row["lang"] == self.lang]

        self.by_name = {}
        for row in self.data:
            self.by_name[row["name"]] = {
                "iso2":row["iso2"],
                "sub":row["sub"],
                }

        def ngram_dict():
            return {
                "name": defaultdict(float),
                "total": 0.0
                }

        names = defaultdict(list)
        for row in self.data:
            iso2 = row["iso2"]
            name = row["name"]
            names[iso2].append(name)

        self.ngrams = defaultdict(ngram_dict)
        for iso2, name_list in list(names.items()):
            weight = 1.0 / len(name_list)
            for name in name_list:
                for ngram in text_to_ngrams(name, self.size):
                    self.ngrams[ngram]["name"][name] += weight
                    self.ngrams[ngram]["total"] += weight



    def match(self, text):
        iso2 = None
        sub = None

        row = self.by_name.get(text, None)
        if row:
            iso2, sub = row["iso2"], row["sub"]

        return iso2, sub


    def search_all(self, text):
        candidates = defaultdict(float)

        for ngram in text_to_ngrams(text, self.size):
            matches = self.ngrams.get(ngram, None)
            if not matches:
                continue
            total = matches["total"]
            for name, value in list(matches["name"].items()):
                candidates[name] += float(value) / total

        def score():
            return {
                "value": 0.0,
                }

        high_scores = defaultdict(score)

        for name, value in list(candidates.items()):
            row = self.by_name.get(name, None)
            key = row["iso2"]
            if row["sub"]:
                key += ">"
            if value > high_scores[key]["value"]:
                high_scores[key] = {
                    "iso2": row["iso2"],
                    "value": value,
                    "name": name,
                    "sub": row["sub"],
                }

        high_scores = sorted(high_scores.values(),
                             key=lambda x: x["value"], reverse=True)

        return high_scores


    def search(self, text, insert=None):
        iso2 = None
        sub = None

        result = pick_one(text, self.search_all)
        if result:
            iso2, sub = result

        if insert:
            insert(iso2, sub, self.lang, text)

        return iso2, sub



def pick_one(text, search_func, limit=10):
    search_text = text
    while True:
        high_scores = search_func(search_text)[:limit]
        max_score = None

        sys.stderr.write("\n             Find:  %s\n\n" % repr(text))

        for i, row in enumerate(high_scores):
            if max_score is None:
                max_score = row["value"]
            sys.stderr.write(" %4s:  %10s  %s\n" % (
                i + 1,
                "+" * int(10 * row["value"] / max_score),
                row["name"]
            ))

        sys.stderr.write("\n")
        sys.stderr.write("    0:  None of the above\n")
        sys.stderr.write("   #>:  Confirm text as sub-region of option #\n")
        sys.stderr.write(" Text:  Alternative search string\n")
        sys.stderr.write("\n")

        sys.stderr.write("> ")
        choice = input().strip()
        sys.stderr.write("\n")

        if not choice:
            sys.stderr.write("Please select an option.\n\n")
            continue

        if re.match("^[0-9]+$", choice):
            choice = int(choice) - 1
            sub = False
        elif re.match("^[0-9]+>$", choice):
            choice = int(choice[:-1]) - 1
            sub = True
        else:
            search_text = choice
            continue

        if choice == -1:
            return None

        if not 0 <= choice < len(high_scores):
            sys.stderr.write("Choice out of range.\n\n")
            continue

        row = high_scores[choice]

        return row["iso2"], sub



def clean_text(text):
    text = text.strip()
    text = text.lower()
    text = text.replace("\u2013", "-")
    text = text.replace("/", " ")
    text = text.replace(" - ", " ")
    text = re.compile(r"[^\w '-]+", re.U).sub("", text)
    text = re.compile(r"[\s]+", re.U).sub(" ", text)
    return text



def load_data(source_csv=None):
    data = {}

    def process_line(line):
        line = line[:-1]
        iso2, features, lang, name = line.split("; ")

        sub = ">" in features
        name = clean_text(name)
        assert name

        data[(lang, name)] = {
            "iso2": iso2,
            "sub": sub,
            "lang": lang,
            "name": name,
        }

    path = os.path.join(CONFIG_PATH, ISOSTATE_CSV)
    if not os.path.exists(path):
        path = ISOSTATE_CSV

    with open(path, "r", encoding="utf-8") as csv_fp:
        for line in csv_fp.readlines():
            process_line(line)

    if source_csv:
        if os.path.exists(source_csv):
            with open(source_csv, "r", encoding="utf-8") as csv_fp:
                for line in csv_fp.readlines():
                    process_line(line)

    return list(data.values())



def text_to_ngrams(text, size=3):
    ngrams = []

    if hasattr(size, "__iter__"):
        for value in size:
            ngrams += text_to_ngrams(text, value)
        return ngrams

    text = clean_text(text)

    for word in text.split():
        length = len(word)
        space = " " * (size - 1)
        word = space + word + space
        for i in range(length + size - 1):
            ngrams.append(word[i: i + size])
    return ngrams



def main():
    LOG.addHandler(logging.StreamHandler())

    usage = """%prog SEARCH..."""

    parser = OptionParser(usage=usage)
    parser.add_option(
        "-v", "--verbose", dest="verbose",
        action="count", default=0,
        help="Print verbose information for debugging.")
    parser.add_option(
        "-q", "--quiet", dest="quiet",
        action="count", default=0,
        help="Suppress warnings.")

    (options, args) = parser.parse_args()

    log_level = (logging.ERROR, logging.WARNING, logging.INFO, logging.DEBUG,)[
        max(0, min(3, 1 + options.verbose - options.quiet))]
    LOG.setLevel(log_level)

    if not len(args):
        parser.print_usage()
        sys.exit(1)

    for text in args:
        print(Iso(text) or "")



if __name__ == "__main__":
    main()
