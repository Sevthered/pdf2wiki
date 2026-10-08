# SPDX-FileCopyrightText: 2026 Sevthered <Sevthered@users.noreply.github.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Shapes that more than one test file reads, so the files cannot drift onto different ones."""

import pytest


@pytest.fixture(scope="session")
def block_openers() -> list[str]:
    """Bodies that open a CommonMark block when they stand at the start of a line.

    Not a grammar. The #94 rule in `symbol_pua` does not enumerate these: it keeps the head for
    every body its whitelist does not name. They are here because #94 measured each of them. The
    counter tests in `test_symbol_pua_positions.py` and the cmark test in
    `test_symbol_pua_rendering.py` both read this ONE list. A fixture and not an import, so the
    two files stay independent of how pytest puts `tests/` on the import path.
    """
    return [
        "# head",
        "###### h6",
        "- item",
        "+ item",
        "* item",
        "1. one",
        "1) one",
        "> quote",
        "```",
        "~~~",
        "*** ",
        "___ ",
        "---",
        "===",
        "<div>",
        "<table>",
        "[ref]: /url",  # a link reference definition, which renders as nothing at all
    ]
