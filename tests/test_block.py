"""Block adapter round-trip identity — the foundation the Stage-6 typed-Block refactor rests on.

The raw-dict-backed `Block` must be transparent: `to_dict()` returns exactly the dict it was built
from, preserving key order AND unmodelled MinerU passthrough keys, so `blocks.json` stays
byte-identical. If this holds, migrating consumers from `b["k"]` to `b.k` cannot change the output.
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pdf2wiki.convert.block import Block

# a block carrying a key pdf2wiki does NOT model (`some_mineru_key`) + one it does — both must survive
SAMPLE = {
    "type": "table",
    "bbox": [1, 2, 3, 4],
    "abs_page": 7,
    "table_body": "<table/>",
    "some_mineru_key": "passthrough",
    "table_caption": ["Cap"],
    "_imgdir": "/pass/dir",
}


def test_block_round_trip_is_byte_identical():
    b = Block.from_dict(dict(SAMPLE))
    assert b.to_dict() == SAMPLE  # content identical (incl. passthrough key)
    assert json.dumps(b.to_dict()) == json.dumps(SAMPLE)  # byte-identical: key order preserved


def test_block_typed_accessors_read():
    b = Block.from_dict(
        {
            "type": "code",
            "sub_type": "python",
            "abs_page": 3,
            "code_body": "x=1",
            "_code_flag": True,
        }
    )
    assert b.type == "code" and b.sub_type == "python" and b.abs_page == 3
    assert b.code_body == "x=1"
    assert b.code_flag is True and b.indent_flag is False


def test_block_setters_write_through_to_raw():
    b = Block.from_dict({"type": "code"})
    b.abs_page = 5
    b.code_flag = True
    b.imgdir = "/x"
    assert b.to_dict() == {"type": "code", "abs_page": 5, "_code_flag": True, "_imgdir": "/x"}
