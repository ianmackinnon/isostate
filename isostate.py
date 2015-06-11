#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import re
import sys
import csv
import shutil
import codecs
import logging

from optparse import OptionParser
from collections import defaultdict



log = logging.getLogger('isostate')

config_path = u"/etc/isostate"

isostate_csv = u"isostate.csv"
sources_path = u"sources"

default_lang = "en"
default_name = "short"



class LookupNotFoundException(Exception):
    pass

class NameNotFoundException(Exception):
    pass



def utf_8_encoder(unicode_csv_data):
    for line in unicode_csv_data:
        yield line.encode('utf-8')



def unicode_csv_reader(unicode_csv_data, dialect=csv.excel, **kwargs):
    # csv.py doesn't do Unicode; encode temporarily as UTF-8:
    csv_reader = csv.reader(utf_8_encoder(unicode_csv_data),
                            dialect=dialect, **kwargs)
    for row in csv_reader:
        # decode UTF-8 back to Unicode, cell by cell:
        yield [unicode(cell, 'utf-8').strip() for cell in row]



def codes(name=default_name, lang=default_lang, source=None):
    codes = {}
    reader = Iso.source_iter(name, lang, source)
    for row in reader:
        if not len(row):
            continue
        iso2, features, lang, name = row
        codes[iso2] = name
    return codes



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
    def key(name=default_name, lang=default_lang):
        return "%s.%s" % (name, lang)


    @classmethod
    def source_iter(cls, name=default_name, lang=default_lang, source=None):
        key = cls.key(name, lang)
        if source is None:
            source = "1.%s.csv" % key
            path = os.path.join(config_path, sources_path, source)
            if not os.path.exists(path):
                path = os.path.join(sources_path, source)
        else:
            path = source

        try:
            csv_data = codecs.open(path, "r", "utf-8")
        except Exception as e:
            log.error("Could not open file '%s' for name '%s' and language '%s'." % (path, name, lang))
            raise e
            
        reader = unicode_csv_reader(csv_data, delimiter=';')
        return reader
        

    def add_lookup(self, name=default_name, lang=default_lang, source=None):
        key = self.key(name, lang)
        reader = self.source_iter(name, lang, source)
        for row in reader:
            if not len(row):
                continue
            iso2, features, lang, name = row
            if not key in self._lookup:
                self._lookup[key] = {}
            self._lookup[key][iso2] = name


    def name(self, iso2, name=default_name, lang=default_lang):
        key = self.key(name, lang)
        if not key in self._lookup:
            raise LookupNotFoundException("No lookup found with key '%s'." % key)
        if not iso2 in self._lookup[key]:
            raise NameNotFoundException("No name found for code '%s' in lookup '%s'." % (iso2, key))
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
            cache_csv = codecs.open(self._cache_path, "a", "utf-8")
            cache_csv.write("%2s; %s; %2s; %s\n" % (
                    iso2 or "  ",
                    sub and ">" or "",
                    lang,
                    name,
                    ))
        data = load_data(self._cache_path)
        self._source.reload(data)



class SourceText(object):
    def __init__(self, data, lang=default_lang, sub=False, size=(3, 5, 7)):
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
        for iso2, name_list in names.items():
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
            for name, value in matches["name"].items():
                candidates[name] += float(value) / total

        def score():
            return {
                "value": 0.0,
                }

        high_scores = defaultdict(score)

        for name, value in candidates.items():
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
        
        high_scores = [(value["value"], value) for key, value in high_scores.items()]

        high_scores.sort(reverse=True)

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
        high_scores = search_func(search_text)[:9]
        max_score = None

        sys.stderr.write("\n             Find:  %s\n\n" % repr(text))

        for i, (score, row) in enumerate(high_scores):
            if max_score is None:
                max_score = score
            score = "+" * int(10 * score / max_score)
            sys.stderr.write(" %4s:  %10s  %s\n" % (i + 1, score, row["name"]))

        sys.stderr.write("\n")
        sys.stderr.write("    0:  None of the above\n")
        sys.stderr.write("   #>:  Confirm text as sub-region of option #\n")
        sys.stderr.write(" Text:  Alternative search string\n")
        sys.stderr.write("\n")

        sys.stderr.write("> ")
        choice = raw_input().strip()
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

        if not (0 <= choice < len(high_scores)):
            sys.stderr.write("Choice out of range.\n\n")
            continue

        row = high_scores[choice][1]

        return row["iso2"], sub



def clean_text(text):
    text = text.strip()
    text = text.lower()
    text = text.replace(u"\u2013", "-")
    text = re.compile("[\s-]+", re.U).sub(" ", text)
    text = re.compile("[^\w ']+", re.U).sub("", text)
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
        
    path = os.path.join(config_path, isostate_csv)
    if os.path.exists(path):
        csv = codecs.open(path, "r", "utf-8")
    else:
        csv = codecs.open(isostate_csv, "r", "utf-8")

    for line in csv.readlines():
        process_line(line)

    if source_csv:
        if os.path.exists(source_csv):
            csv = codecs.open(source_csv, "r", "utf-8")
            for line in csv.readlines():
                process_line(line)
        
    data = data.values()

    return data



def text_to_ngrams(text, size=3):
    ngrams = []

    if hasattr(size, "__iter__"):
        for value in size:
            ngrams += text_to_ngrams(text, value)
        return ngrams
        
    text = clean_text(text)

    for word in text.split():
        length = len(word)
        space = u" " * (size - 1)
        word = space + word + space
        for i in xrange(length + size - 1):
            ngrams.append(word[i: i + size])
    return ngrams



if __name__ == "__main__":
    log.addHandler(logging.StreamHandler())

    usage = """%prog SEARCH..."""

    parser = OptionParser(usage=usage)
    parser.add_option("-v", "--verbose", action="count", dest="verbose",
                      help="Print verbose information for debugging.", default=0)
    parser.add_option("-q", "--quiet", action="count", dest="quiet",
                      help="Suppress warnings.", default=0)

    (options, args) = parser.parse_args()
    args = [arg.decode(sys.getfilesystemencoding()) for arg in args]

    log_level = (logging.ERROR, logging.WARNING, logging.INFO, logging.DEBUG,)[
        max(0, min(3, 1 + options.verbose - options.quiet))]

    log.setLevel(log_level)

    if not len(args):
        parser.print_usage()
        sys.exit(1)

    for text in args:
        print iso(text) or ""


        
