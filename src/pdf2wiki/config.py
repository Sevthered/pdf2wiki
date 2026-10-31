# SPDX-FileCopyrightText: 2026 Sevthered <Sevthered@users.noreply.github.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Configuration for pdf2wiki.

Resolution order (first hit wins, per key):
  1. CLI flags
  2. ./pdf2wiki.toml (project-local)
  3. ~/.config/pdf2wiki/config.toml (user)
  4. built-in defaults below

All values that were once hardcoded for a specific machine live here instead.
"""

from __future__ import annotations

import os
import shutil
import tomllib
from dataclasses import dataclass, field, fields
from typing import Any


@dataclass
class MineruConfig:
    binary: str = ""  # empty -> discover `mineru` on PATH
    model_source: str = "huggingface"  # MINERU_MODEL_SOURCE
    effort: str = "high"  # hybrid-engine effort for the VLM pass
    hybrid_server_url: str = ""  # empty -> local hybrid-engine (GPU). Set -> offload ONLY the
    #                                     hybrid VLM pass to this OpenAI-compatible MinerU server
    #                                     (`hybrid-http-client -u URL`); pipeline stays local (CPU ok).
    #                                     BYO server; no auth (front with a reverse proxy). See
    #                                     decision-pdf2wiki-api-hybrid-offload.

    def resolve_binary(self) -> str:
        if self.binary:
            return os.path.expanduser(self.binary)
        found = shutil.which("mineru")
        if not found:
            raise FileNotFoundError(
                "mineru CLI not found on PATH. Install MinerU (https://github.com/opendatalab/MinerU) "
                "or set [mineru].binary in pdf2wiki.toml"
            )
        return found


@dataclass
class ConvertConfig:
    out_root: str = "~/pdf2wiki/out"
    workdir: str = (
        "~/.pdf2wiki/run"  # clean cwd for MinerU subprocesses (see README: stdlib-shadow gotcha)
    )
    timeout: int = 7200  # seconds per MinerU pass (local conversion)
    gap: int = 3  # merge nearby rich pages into one hybrid run if gap <= this
    seg: int = 40  # pipeline segment size (pages) for chunked passes
    maxrun: int = 25  # cap on a single hybrid run length (pages)
    tiny_px2: int = 2500  # ignore images smaller than this (px^2) when profiling pages


@dataclass
class QaConfig:
    root: str = "~/pdf2wiki/qa"
    dpi: int = 140
    seed: int = 42
    pages: int = 20


@dataclass
class RemoteConfig:
    host: str = ""  # ssh destination (alias or user@host); empty -> local execution
    books_dir: str = ""  # directory on the remote host holding the PDFs
    workdir: str = "~/pdf2wiki-remote"  # remote working directory (converter output lives under it)
    connect_timeout: int = 8
    convert_timeout: int = 7200
    fetch_timeout: int = 600  # bound each scp artifact pull (Timeouts-Pattern: every remote call)
    reap_grace: int = 120  # extra local wait over the remote `timeout Ns` reaper before SIGKILL
    max_consec_fail: int = 3  # consecutive book failures before the batch circuit breaker re-probes


@dataclass
class MineruCloudConfig:
    # Fully-managed mineru.net Cloud converter (`--mineru-cloud`). No GPU, no local MinerU — the PDF is
    # uploaded to the OpenDataLab cloud and parsed there. See decision/improvement notes on data egress.
    token: str = ""  # empty -> read env MINERU_API_TOKEN, then token_file. PREFER env
    #                                     or token_file: an inline token in a project pdf2wiki.toml risks
    #                                     being committed (pdf2wiki.toml is gitignored for this reason).
    token_file: str = ""  # optional path to a file holding the Bearer token (kept out of VCS)
    base_url: str = "https://mineru.net/api/v4"
    # pipeline (default) = text-layer, byte-clean code but FLAT indent. vlm = indent + tables/Mermaid but
    # CORRUPTS code (Qwen2-VL Chinese-token drift, e.g. orElseThrow -> "二等奖", findFirst -> "找到了";
    # A/B-proven 2026-07-22, bug-vlm-code-hallucination). Default pipeline for code safety.
    model_version: str = "pipeline"  # pipeline | vlm | MinerU-HTML
    language: str = "en"  # mineru.net default is "ch"; our books are English
    extra_formats: list[str] = field(default_factory=list)  # e.g. ["latex"] for formula-heavy books
    poll_timeout: int = 1800  # seconds to wait for the cloud task
    max_pages: int = 200  # mineru.net Precision hard limit per file
    retries: int = 3  # attempts for each one-shot HTTP call (submit/upload/download)
    retry_base_delay: float = 2.0  # exponential backoff base (s); jittered — Backoff-Retries
    poll_max_transient: int = 5  # consecutive transient poll errors tolerated before giving up


@dataclass
class OutputConfig:
    vault: str = ""  # optional: final placement root (e.g. an Obsidian vault)


@dataclass
class Config:
    mineru: MineruConfig = field(default_factory=MineruConfig)
    mineru_cloud: MineruCloudConfig = field(default_factory=MineruCloudConfig)
    convert: ConvertConfig = field(default_factory=ConvertConfig)
    qa: QaConfig = field(default_factory=QaConfig)
    remote: RemoteConfig = field(default_factory=RemoteConfig)
    output: OutputConfig = field(default_factory=OutputConfig)


SECTIONS = tuple(f.name for f in fields(Config))  # derived once: the sections a file may set


def config_candidates(explicit_path: str | None = None) -> list[str]:
    """The config files load_config reads, in merge order (later files win). One list, so a tool
    that reports on the search (`pdf2wiki doctor`) cannot drift from the search itself."""
    if explicit_path:
        return [explicit_path]
    return [os.path.expanduser("~/.config/pdf2wiki/config.toml"), "pdf2wiki.toml"]


@dataclass
class ConfigProblem:
    path: str
    # "read" (OSError) | "parse" (bad TOML or encoding) | "type" (wrong section or value)
    # | "missing" (an explicit --config path that does not exist)
    kind: str
    message: str
    section: str = ""  # kind "type" only
    key: str = ""  # kind "type" only; empty when the whole section is the wrong type
    expected: str = ""  # kind "type" only


class ConfigError(ValueError):
    """A config file cannot be used. The message names the file and says what failed: a missing
    explicit file, a read or parse error, or a value or section of the wrong type (then it names
    the key, the expected type and the actual type)."""

    def __init__(self, problem: ConfigProblem) -> None:
        what = {"read": "cannot read: ", "parse": "cannot parse: ", "missing": ""}.get(
            problem.kind, ""
        )
        super().__init__(f"{problem.path}: {what}{problem.message}")
        self.problem = problem


@dataclass
class ConfigFileInfo:
    path: str
    exists: bool
    data: dict[str, Any] | None = None  # the parsed file; None when it could not be read


@dataclass
class ConfigReport:
    config: Config
    files: list[ConfigFileInfo] = field(default_factory=list)
    problems: list[ConfigProblem] = field(default_factory=list)
    explicit: bool = False  # the path came from --config


def _type_name(template: Any) -> str:
    return {bool: "a boolean", int: "an integer", float: "a number", list: "a list"}.get(
        type(template), "a string"
    )


def _value_ok(template: Any, value: Any) -> bool:
    """Does `value` have the type of the field's default? bool is not an int here, and an int is
    fine for a float field (TOML `2` is an int)."""
    if isinstance(template, bool):
        return isinstance(value, bool)
    if isinstance(template, int):
        return isinstance(value, int) and not isinstance(value, bool)
    if isinstance(template, float):
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if isinstance(template, list):
        return isinstance(value, list) and all(isinstance(v, str) for v in value)
    return isinstance(value, str)


def load_config_report(explicit_path: str | None = None, strict: bool = False) -> ConfigReport:
    """The one place config files are read, merged and checked.

    Both modes check every section and value against the type of its DEFAULT (never the merged
    value, which an earlier file may have set), so a wrong type stops early and clearly instead
    of crashing later (`subprocess.run(timeout="7200")`).
    strict=True is for every command except doctor: the first problem raises ConfigError. That is
    an explicit --config file that does not exist, a file that cannot be read or parsed, and a
    section or value of the wrong type. strict=False never raises. It skips what it cannot use
    (the key keeps its default) and lists each as a problem. `pdf2wiki doctor` reports them."""
    report = ConfigReport(Config(), explicit=bool(explicit_path))
    cfg = report.config
    defaults = Config()

    def problem(p: ConfigProblem) -> None:
        if strict:
            raise ConfigError(p)
        report.problems.append(p)

    for path in config_candidates(explicit_path):
        if not os.path.exists(path):
            if strict and explicit_path:  # the default search paths stay optional
                raise ConfigError(ConfigProblem(path, "missing", "--config file does not exist"))
            report.files.append(ConfigFileInfo(path, False))
            continue
        try:
            with open(path, "rb") as f:
                data = tomllib.load(f)
        except (OSError, ValueError) as e:  # ValueError: TOMLDecodeError and UnicodeDecodeError
            report.files.append(ConfigFileInfo(path, True))
            problem(ConfigProblem(path, "read" if isinstance(e, OSError) else "parse", str(e)))
            continue
        report.files.append(ConfigFileInfo(path, True, data))
        for section in SECTIONS:
            if section not in data:
                continue
            if not isinstance(data[section], dict):
                msg = f"[{section}] must be a table, not {type(data[section]).__name__}"
                problem(ConfigProblem(path, "type", msg, section, "", "a table"))
                continue
            obj = getattr(cfg, section)
            fresh = getattr(defaults, section)
            valid = {f.name for f in fields(obj)}
            for key, value in data[section].items():
                if key not in valid:
                    continue
                template = getattr(fresh, key)
                if not _value_ok(template, value):
                    exp = _type_name(template)
                    msg = f"[{section}] {key} must be {exp}, not {type(value).__name__}"
                    problem(ConfigProblem(path, "type", msg, section, key, exp))
                    continue
                if isinstance(template, float) and isinstance(value, int):
                    value = float(value)
                setattr(obj, key, value)
    return report


def load_config(explicit_path: str | None = None, strict: bool = True) -> Config:
    """Load config, merging user config then project-local config over defaults.
    See load_config_report for the strict and lenient modes."""
    return load_config_report(explicit_path, strict).config
