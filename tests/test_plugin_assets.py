# SPDX-FileCopyrightText: 2026 Sevthered <Sevthered@users.noreply.github.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Checks for the llm-wiki plugin assets under `plugin/`.

The `knowledge-query` skill and the `knowledge-researcher` agent both run the coverage gate through
one script, `plugin/scripts/vault_coverage.py`, and the skill hands its output to the agent. These
tests pin that both assets call the script, that the assets keep their sections, and that the
script counts what its docstring says on a small vault.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugin"
AGENT = PLUGIN / "agents" / "knowledge-researcher.md"
SKILL = PLUGIN / "skills" / "knowledge-query" / "SKILL.md"
SCRIPT = PLUGIN / "scripts" / "vault_coverage.py"
CALL = "python3 ${CLAUDE_PLUGIN_ROOT}/scripts/vault_coverage.py <vault>"


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("vault_coverage", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["vault_coverage"] = module
    write = sys.dont_write_bytecode
    sys.dont_write_bytecode = True  # no __pycache__ inside the shipped plugin folder
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = write
    return module


vc = load_script()


@pytest.mark.parametrize("path", [AGENT, SKILL])
def test_asset_calls_the_one_script(path: Path) -> None:
    assert CALL in path.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("path", "needles"),
    [
        (
            AGENT,
            [
                "## Step 0",
                "**COVERED**",
                "**PASSING**",
                "**NONE**",
                "**return at once**",
                "## Method",
                "## Book folders",
                "<book-slug>-index.md",
                "## Read budget",
                "## Output contract",
                "**Coverage**",
                "**Not covered**",
            ],
        ),
        (
            SKILL,
            [
                "## Coverage pre-check",
                "(COVERED)",
                "(PASSING)",
                "(NONE)",
                "## Vault scope",
                "## Navigation protocol",
                "<book>-index.md",
                "## Context discipline",
                "## Trust markers",
            ],
        ),
    ],
)
def test_asset_keeps_its_sections(path: Path, needles: list[str]) -> None:
    text = path.read_text(encoding="utf-8")
    missing = [n for n in needles if n not in text]
    assert not missing, f"{path.name} lost: {missing}"


def test_plugin_version_is_in_the_changelog() -> None:
    version = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text())["version"]
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"llm-wiki plugin {version}" in changelog


# --- the script ----------------------------------------------------------------------------------


def test_headings_skip_frontmatter_and_code_fences() -> None:
    text = "\n".join(
        [
            "---",
            "# a YAML comment, not a heading",
            "title: x",
            "---",
            "# Real one",
            "```bash",
            "# a comment",
            "```",
            "````md",
            "```bash",
            "# inside a nested fence",
            "```",
            "## still inside the outer fence",
            "````",
            "~~~",
            "```",
            "# tilde fence, a ``` line does not close it",
            "~~~",
            "#### Deep heading ##",
            "####### seven marks is not a heading",
            "#nospace is not a heading",
        ]
    )
    assert vc.headings(text) == ["Real one", "Deep heading"]


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    wiki = tmp_path / "wiki"
    (wiki / "concepts" / "sub").mkdir(parents=True)
    (wiki / "entities").mkdir()
    pages = {
        "concepts/Retry-Pattern.md": "# Retry Pattern\n\nBack off and retry.\n",
        "concepts/Timeouts.md": "# Timeouts\n\n```bash\n# retry on 503\n```\n",
        "concepts/sub/Nested-Topic.md": "# Nested\n\n#### Exponential backoff\n",
        "concepts/Hole-Punching.md": "# NAT Traversal\n\nThrough a NAT.\n",
        "concepts/Cpp-Basics.md": "# C++ Basics\n\n# Concrete notes\n",
        "concepts/Wrapped.md": "# Wrapped\n\nA circuit\nbreaker trips.\n",
        "entities/Concept-Drift.md": "# Concept Drift\n\nA model ages.\n",
        "entities/Quickstart.md": "# Quickstart\n\nRun it quickly.\n",
    }
    for rel, text in pages.items():
        (wiki / rel).write_text(text, encoding="utf-8")
    return tmp_path


def run(vault: Path, term: str) -> tuple[str, list[str]]:
    rx = re.compile(term, re.IGNORECASE | re.MULTILINE)
    summary, detail = vc.count(vc.load(vault), term, rx)
    return str(summary), list(detail)


def summary(vault: Path, term: str) -> str:
    return run(vault, term)[0]


def test_counts_files_without_regard_to_case(vault: Path) -> None:
    # Retry-Pattern: name, heading, body. Nested-Topic: an H4 heading. Timeouts: a code comment only.
    assert summary(vault, "retry|backoff") == "retry|backoff 1/2/3 COVERED"
    assert summary(vault, "RETRY") == "RETRY 1/1/2 COVERED"


def test_code_comment_is_no_heading(vault: Path) -> None:
    assert summary(vault, "503") == "503 0/0/1 PASSING"


def test_anchors_work_on_lines_and_on_heading_text(vault: Path) -> None:
    assert summary(vault, "^retry") == "^retry 1/1/0 COVERED"  # body lines start with "#"
    assert summary(vault, "^nat traversal$") == "^nat traversal$ 0/1/0 COVERED"


def test_whole_word_term_matches_a_leading_heading_word(vault: Path) -> None:
    assert summary(vault, r"\bnat\b") == r"\bnat\b 0/1/1 COVERED"
    assert summary(vault, "quic") == "quic 1/1/1 COVERED"
    assert summary(vault, r"\bquic\b") == r"\bquic\b 0/0/0 NONE"


def test_regex_escapes_survive(vault: Path) -> None:
    # c\+\+ must not become c++ ("one or more c"), which would match "Concrete".
    assert summary(vault, r"c\+\+") == r"c\+\+ 0/1/1 COVERED"


def test_no_folder_header_counts_as_a_page(vault: Path) -> None:
    assert summary(vault, "concept") == "concept 1/1/1 COVERED"
    assert summary(vault, "entit") == "entit 0/0/0 NONE"


def test_passing_term_shows_its_match_text(vault: Path) -> None:
    assert run(vault, "503")[1] == ["body: concepts/Timeouts.md: # retry on 503"]
    # a match across a line break still shows text
    assert run(vault, r"circuit\s+breaker")[1] == [
        "body: concepts/Wrapped.md: A circuit breaker trips."
    ]


def test_long_lists_are_capped(tmp_path: Path) -> None:
    concepts = tmp_path / "wiki" / "concepts"
    concepts.mkdir(parents=True)
    for i in range(20):
        (concepts / f"Topic-{i:02}.md").write_text(f"# Topic {i}\n", encoding="utf-8")
    detail = run(tmp_path, "topic")[1]
    assert detail.count("filename: ... 5 more") == 1
    assert detail.count("heading: ... 5 more") == 1
    assert len(detail) == 2 * vc.MAX_LINES + 2


def test_main_prints_a_coverage_line(vault: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert vc.main([str(vault), "retry", "wireguard"]) == 0
    last = capsys.readouterr().out.strip().splitlines()[-1]
    assert last == "Coverage: retry 1/1/2 COVERED; wireguard 0/0/0 NONE"


def test_bad_regex_fails_before_any_output(vault: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert vc.main([str(vault), "retry", "("]) == 2
    assert capsys.readouterr().out == ""


def test_main_rejects_a_missing_wiki_and_no_terms(tmp_path: Path) -> None:
    assert vc.main([str(tmp_path / "nowhere"), "x"]) == 2
    assert vc.main([]) == 2
