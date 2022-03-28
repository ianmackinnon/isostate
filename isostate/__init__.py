#!/usr/bin/env python3

import os
import re
import sys
import csv
import logging
import pkg_resources
from typing import Union
from pathlib import Path
from argparse import ArgumentParser
from collections import defaultdict
from importlib.resources import files



__version__ = pkg_resources.require("isostate")[0].version

LOG = logging.getLogger('isostate')


PACKAGE_DATA_PATH = files('isostate').joinpath('data')
DEFAULT_CSV_PATH = PACKAGE_DATA_PATH.joinpath('isostate.csv')

SOURCE_BASENAME_RE = r"^1\.([a-z-]+)\.([a-z]{2})\.csv$"

DEFAULT_LANG = "en"
DEFAULT_NAME = "short"



class LookupNotFoundException(Exception):
    pass

class NameNotFoundException(Exception):
    pass



def get_source_dict() -> dict[tuple[str, str]: Path]:
    path = PACKAGE_DATA_PATH
    source_list = []
    for source_path in sorted(path.glob("*.csv")):
        match = re.compile(SOURCE_BASENAME_RE).match(source_path.name)
        if not match:
            continue
        source_list.append((match.groups(), source_path))
    return dict(sorted(source_list))



def codes(name=DEFAULT_NAME, lang=DEFAULT_LANG, source=None):
    code_dict = {}
    reader = Iso.source_iter(name, lang, source)
    for row in reader:
        if not len(row):
            continue
        iso2, _features, lang, name = row
        code_dict[iso2] = name
    return code_dict



class Iso():
    def __init__(
            self,
            source="text",
            cache: Union[None, str, Path] = None,
            batch: bool = False,
    ):
        self._source = None
        self._cache_path = None
        self._lookup = {}
        self._batch = batch

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
    def source_iter(
            cls,
            name: str = DEFAULT_NAME,
            lang: str = DEFAULT_LANG,
            source: Union[None, str, Path] = None
    ):
        if source is None:
            try:
                path = get_source_dict()[(name, lang)]
            except IndexError:
                LOG.error(
                    "Error: no source file available for name `{%s}` and lang `{%s}`.",
                    name, lang
                )
                sys.exit(1)
        else:
            path = Path(source)

        try:
            csv_data = path.open("r", encoding="utf-8")
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
            row = [v.strip() for v in row]
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


    def iso2(
            self,
            text,
            batch: Union[None, bool] = None,
            accept_sub: bool = False,
    ):
        search_text = clean_text(text)

        assert self._source

        iso2, sub = self._source.match(search_text)

        if batch is None:
            batch = self._batch

        if not batch and not iso2:
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



class SourceText():
    def __init__(self, data, lang=DEFAULT_LANG, sub=False, size=(3, 5, 7)):
        """
        size: ngram size
        """

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
            show_name = row["name"]
            if row["sub"]:
                show_name += " (subregion)"
            sys.stderr.write(" %4s:  %10s  %s\n" % (
                i + 1,
                "+" * int(10 * row["value"] / max_score),
                show_name
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

        return row["iso2"], sub or row["sub"]



def clean_text(text):
    text = text.strip()
    text = text.lower()
    text = text.replace("\u2013", "-")
    text = text.replace("/", " ")
    text = text.replace(" - ", " ")
    text = re.compile(r"[^\w '-]+", re.U).sub("", text)
    text = re.compile(r"[\s]+", re.U).sub(" ", text)
    return text



def load_data(cache_path=None):
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

    path = DEFAULT_CSV_PATH
    n = 0

    with path.open("r", encoding="utf-8") as csv_fp:
        for line in csv_fp.readlines():
            process_line(line)

    LOG.debug(f"Loaded {len(data) - n:d} entries from `{path}`")
    n = len(data)

    if cache_path:
        if os.path.exists(cache_path):
            with open(cache_path, "r", encoding="utf-8") as csv_fp:
                for line in csv_fp.readlines():
                    process_line(line)
        LOG.debug(f"Loaded {len(data) - n:d} entries from `{cache_path}`")


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

    parser = ArgumentParser("Search for ISO country codes.")
    parser.add_argument(
        "--verbose", "-v",
        action="count", default=0,
        help="Print verbose information for debugging.")
    parser.add_argument(
        "--quiet", "-q",
        action="count", default=0,
        help="Suppress warnings.")

    parser.add_argument(
        "--batch", "-b",
        action="store_true",
        help="Non-interactive mode. Search is disabled; only exact matches will be printed.")

    parser.add_argument(
        "--cache", "-c",
        action="store",
        help="Path to cache file.")

    parser.add_argument(
        "--list-sources", "-l",
        action="store_true",
        help="List sources.")

    parser.add_argument(
        "search", metavar="SEARCH",
        nargs="*",
        action="store",
        help="Search string`.")

    args = parser.parse_args()

    level = (logging.ERROR, logging.WARNING, logging.INFO, logging.DEBUG)[
        max(0, min(3, 1 + args.verbose - args.quiet))]
    LOG.setLevel(level)

    if args.list_sources:
        for (name, lang) in get_source_dict():
            print(f"{name}.{lang}")
        return

    if not args.search:
        LOG.warning("No search terms given. Nothing to do.")
        sys.exit(0)

    iso = Iso(cache=args.cache, batch=args.batch)

    iso.add_lookup("short", "en")
    for needle in args.search:
        iso2 = iso.iso2(needle)
        short_en = iso.name(iso2, "short", "en")
        print("%s\t%s" % (iso2, short_en))
