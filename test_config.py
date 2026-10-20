"""Run: python test_config.py   (no browser, no network, no real key)."""
import os
import tempfile
from pathlib import Path

import config

KEYS = ["TCFG_PLAIN", "TCFG_DQ", "TCFG_SQ", "TCFG_EXPORT", "TCFG_SPACED",
        "TCFG_EQ", "TCFG_KEEP", "TCFG_BOM", "TCFG_COMMENTED"]


def clean():
    for k in KEYS:
        os.environ.pop(k, None)


def load(text):
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / ".env"
        p.write_text(text, encoding="utf-8")
        config.load_env_file(p)


clean()
os.environ["TCFG_KEEP"] = "from-real-env"
load("""# a comment

TCFG_PLAIN=abc
TCFG_DQ="double quoted"
TCFG_SQ='single quoted'
export TCFG_EXPORT=exported
  TCFG_SPACED  =  spaced value
TCFG_EQ=a=b=c
TCFG_KEEP=from-file
#TCFG_COMMENTED=no
not a pair line
=novalue
""")
assert os.environ["TCFG_PLAIN"] == "abc"
assert os.environ["TCFG_DQ"] == "double quoted"
assert os.environ["TCFG_SQ"] == "single quoted"
assert os.environ["TCFG_EXPORT"] == "exported"
assert os.environ["TCFG_SPACED"] == "spaced value"
assert os.environ["TCFG_EQ"] == "a=b=c"
assert os.environ["TCFG_KEEP"] == "from-real-env"      # real environment wins
assert "TCFG_COMMENTED" not in os.environ
assert "" not in os.environ

clean()
load("\ufeffTCFG_BOM=bom-ok\n")                        # file starting with a BOM
assert os.environ["TCFG_BOM"] == "bom-ok"

with tempfile.TemporaryDirectory() as d:               # missing file: no error
    config.load_env_file(Path(d) / "nope.env")

clean()
print("test_config: all passed")
