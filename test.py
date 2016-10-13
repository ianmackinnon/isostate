#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import logging
from optparse import OptionParser

import isostate



LOG = logging.getLogger('TEST')


CASES = [
    "Korea (south)",
    "DR Congo ",
    "Marshall",
]



def test():
    iso = isostate.Iso(cache="/tmp/isostate.csv")
    iso.add_lookup("short", "en")
    for case in CASES:
        print(case)
        iso2 = iso.iso2(case)
        print(iso2)
        print(iso.name(iso2, "short", "en"))



def main():
    LOG.addHandler(logging.StreamHandler())

    usage = """%prog"""

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
    args = [arg.decode(sys.getfilesystemencoding()) for arg in args]

    log_level = (logging.ERROR, logging.WARNING, logging.INFO, logging.DEBUG,)[
        max(0, min(3, 1 + options.verbose - options.quiet))]
    LOG.setLevel(log_level)

    if not len(args) == 0:
        parser.print_usage()
        sys.exit(1)

    test()



if __name__ == "__main__":
    main()
