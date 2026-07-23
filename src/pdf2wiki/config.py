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


def _apply_section(obj: Any, data: dict[str, Any]) -> None:
    valid = {f.name for f in fields(obj)}
    for k, v in data.items():
        if k in valid:
            setattr(obj, k, v)


def load_config(explicit_path: str | None = None) -> Config:
    """Load config, merging user config then project-local config over defaults."""
    cfg = Config()
    candidates = []
    if explicit_path:
        candidates = [explicit_path]
    else:
        candidates = [
            os.path.expanduser("~/.config/pdf2wiki/config.toml"),
            "pdf2wiki.toml",
        ]
    for path in candidates:
        if not os.path.exists(path):
            continue
        with open(path, "rb") as f:
            data = tomllib.load(f)
        for section_name in ("mineru", "mineru_cloud", "convert", "qa", "remote", "output"):
            if section_name in data:
                _apply_section(getattr(cfg, section_name), data[section_name])
    return cfg
