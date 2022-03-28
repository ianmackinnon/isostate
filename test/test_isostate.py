import os
from pathlib import Path

import pytest

from isostate import Iso



CASES = {
    "match-exact-marshall": {
        "text": "Marshall Islands",
        "iso2": "MH",
        "name": "Marshall Islands",
    },
    "match-case-whitespace-marshall": {
        "text": " marshall islands ",
        "iso2": "MH",
        "name": "Marshall Islands",
    },
    "missing-korea": {
        "text": "Korea (south)",
    },
    "match-exact-korea": {
        "text": "republic of Korea",
    },
    "missing-dr-congo": {
        "text": "DR Congo",
    },
    "match-case-dr-congo": {
        "text": "DEMOCRATIC REPUBLIC OF THE CONGO",
    },

    "match-exact-cache-marshall": {
        "text": "marshall",
        "iso2": "MH",
        "name": "Marshall Islands",
        "cache": "cache.marshall.1.csv",
    },
}




@pytest.mark.parametrize("case_key", list(CASES))
def test_no_cache_batch(request, case_key):
    case = CASES[case_key]

    cache_path = None
    if cache := case.get("cache", None):
        cache_path = Path(request.fspath.dirname) / cache

    iso = Iso(batch=True, cache=cache_path)
    iso.add_lookup("short", "en")

    iso2 = iso.iso2(case["text"])
    name = None
    if iso2:
        name = iso.name(iso2, "short", "en")
        assert name

    assert iso2 == case.get("iso2", None)
    assert name == case.get("name", None)
