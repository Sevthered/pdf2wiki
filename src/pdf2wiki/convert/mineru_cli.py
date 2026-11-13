# SPDX-FileCopyrightText: 2026 Sevthered <Sevthered@users.noreply.github.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The MinerU versions that pdf2wiki can drive, and how to read the version of a `mineru` binary.

pdf2wiki drives the MinerU 3.x CLI (`mineru -p … -b pipeline|hybrid-engine -s … -e …`, 3.4 or later
for `hybrid-engine` and `--effort`) and reads its `content_list.json`. MinerU 4.0 replaced that CLI
with subcommands (`mineru parse`) and the backends with quality tiers, so a 4.x `mineru` rejects `-p`
and every pass fails. `convert` and `doctor` both use this module, so the bounds live in one place.
"""

from __future__ import annotations

import re

MIN = (3, 4)
MAX = (4, 0)  # exclusive
# MinerU 4 has usage telemetry, on by default. It reads this variable
# (`mineru/doclib/telemetry/service.py` in 4.2.1). Every MinerU subprocess that pdf2wiki starts sets
# it. MinerU 3.x ignores it.
TELEMETRY_OFF = {"MINERU_TELEMETRY_DISABLED": "1"}
# The text that a 4.x `mineru` prints when it gets the 3.x options: the safety net when the version
# could not be read before the pass.
NO_3X_CLI = "No such option: -p"

# `mineru, version 3.4.2` (3.x); `MinerU version: 4.2.1` or `MinerU 版本: 4.2.1` (4.x, a translated
# label, `mineru/utils/translations.py`). Not `mineru.backend…` or `mineru-openai-server`.
_MINERU_LINE = re.compile(r"^\s*mineru(?=[,\s])", re.IGNORECASE)
_NUMBER = re.compile(r"(\d+)\.(\d+)")


def read_version(text: str) -> tuple[tuple[int, int], str] | None:
    """The (major, minor) in the output of `mineru --version`, and the line that holds it. Read only
    from a line that starts with the word `mineru`, so a banner or a warning line (`torch 2.11.0`)
    cannot give the version. None: no such line."""
    for line in text.splitlines():
        if _MINERU_LINE.match(line):
            m = _NUMBER.search(line)
            if m:
                return (int(m[1]), int(m[2])), line.strip()
    return None


def parse_version(text: str) -> tuple[int, int] | None:
    """The (major, minor) of `read_version`."""
    found = read_version(text)
    return found[0] if found else None


def unsupported(version: tuple[int, int]) -> str | None:
    """Why pdf2wiki cannot drive this MinerU version, or None when it can."""
    a, b = version
    if version < MIN:
        return f"MinerU {a}.{b} is older than {MIN[0]}.{MIN[1]}"
    if version >= MAX:
        return f"MinerU {a}.{b} has another CLI: pdf2wiki supports MinerU 3.4 to 3.x only"
    return None


def fix(hybrid_offload: bool | None = False) -> str:
    """The install command. A client that offloads the hybrid pass needs no local vLLM. None: the
    caller does not know, so both commands."""
    req = f">={MIN[0]}.{MIN[1]},<{MAX[0]}"
    if hybrid_offload is None:
        return (
            f'uv pip install "mineru[all]{req}" '
            f'(or "mineru[core]{req}" on a client that offloads the hybrid pass)'
        )
    extra = "core" if hybrid_offload else "all"
    return f'uv pip install "mineru[{extra}]{req}"'
