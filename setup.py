from pathlib import Path
from setuptools import setup, find_packages

setup(
    name="isostate",
    version=Path("VERSION").read_text(encoding="utf-8").strip(),
    packages=find_packages(),
    package_data={
        "isostate": [
            "data/*.csv",
        ],
    },
)
