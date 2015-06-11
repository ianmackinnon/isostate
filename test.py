#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import logging

from optparse import OptionParser

import isostate



log = logging.getLogger('TEST')


cases = [
    u"Korea (south)",
    u"DR Congo ",
    u"Marshall",
]



def test():
    iso = isostate.Iso(cache="/tmp/isostate.csv")
    iso.add_lookup("short", "en")
    for case in cases:
        print case
        print iso.iso2(case)
        print iso.name(case, "short", "en")



if __name__ == "__main__":
    log.addHandler(logging.StreamHandler())

    usage = """%prog"""

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

    if not len(args) == 0:
        parser.print_usage()
        sys.exit(1)

    test()
