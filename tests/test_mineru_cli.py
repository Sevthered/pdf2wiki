# SPDX-FileCopyrightText: 2026 Sevthered <Sevthered@users.noreply.github.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The MinerU versions that pdf2wiki can drive (`convert.mineru_cli`)."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pdf2wiki.convert import mineru_cli


@pytest.mark.parametrize(
    ("text", "version"),
    [
        ("mineru, version 3.4.2\n", (3, 4)),
        ("MinerU version: 4.2.1\nPython version: 3.12.3\n", (4, 2)),
        ("MinerU 版本: 4.2.1\n", (4, 2)),  # a translated label
        # review: a banner or a warning before the version line cannot give the version
        ("WARNING torch 2.11.0 found\nMinerU version: 4.2.1\n", (4, 2)),
        ("listening on 192.168.111.125\nmineru, version 3.4.2\n", (3, 4)),
        ("\nmineru, version 3.4.2\n", (3, 4)),  # stdout empty, the version on stderr
        # review round 2: a module name or a tool name is not the version line
        ("mineru.backend.vlm: torch 2.11.0\nmineru, version 3.4.2\n", (3, 4)),
        ("mineru-openai-server 0.9\nMinerU version: 4.2.1\n", (4, 2)),
        ("torch 2.11.0\n", None),
        ("", None),
    ],
)
def test_parse_version(text, version):
    assert mineru_cli.parse_version(text) == version


@pytest.mark.parametrize(
    ("version", "supported"),
    [((3, 4), True), ((3, 9), True), ((3, 3), False), ((2, 6), False), ((4, 0), False)],
)
def test_supported_versions(version, supported):
    assert (mineru_cli.unsupported(version) is None) is supported


def test_fix_names_the_extra():
    assert mineru_cli.fix() == 'uv pip install "mineru[all]>=3.4,<4"'
    assert mineru_cli.fix(hybrid_offload=True) == 'uv pip install "mineru[core]>=3.4,<4"'
    both = mineru_cli.fix(None)
    assert '"mineru[all]>=3.4,<4"' in both and '"mineru[core]>=3.4,<4"' in both


def test_read_version_gives_the_version_line():
    text = "WARNING torch 2.11.0\nMinerU version: 4.2.1\n"
    assert mineru_cli.read_version(text) == ((4, 2), "MinerU version: 4.2.1")
