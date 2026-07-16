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


@dataclass
class MineruConfig:
    binary: str = ""                    # empty -> discover `mineru` on PATH
    model_source: str = "huggingface"   # MINERU_MODEL_SOURCE
    effort: str = "high"                # hybrid-engine effort for the VLM pass

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
    workdir: str = "~/.pdf2wiki/run"    # clean cwd for MinerU subprocesses (see README: stdlib-shadow gotcha)
    timeout: int = 7200                 # seconds per MinerU pass (local conversion)
    gap: int = 3                        # merge nearby rich pages into one hybrid run if gap <= this
    seg: int = 40                       # pipeline segment size (pages) for chunked passes
    maxrun: int = 25                    # cap on a single hybrid run length (pages)
    tiny_px2: int = 2500                # ignore images smaller than this (px^2) when profiling pages


@dataclass
class QaConfig:
    root: str = "~/pdf2wiki/qa"
    dpi: int = 140
    seed: int = 42
    pages: int = 20


@dataclass
class RemoteConfig:
    host: str = ""                      # ssh destination (alias or user@host); empty -> local execution
    books_dir: str = ""                 # directory on the remote host holding the PDFs
    workdir: str = "~/pdf2wiki-remote"  # remote working directory (converter output lives under it)
    connect_timeout: int = 8
    convert_timeout: int = 7200


@dataclass
class OutputConfig:
    vault: str = ""                     # optional: final placement root (e.g. an Obsidian vault)


@dataclass
class Config:
    mineru: MineruConfig = field(default_factory=MineruConfig)
    convert: ConvertConfig = field(default_factory=ConvertConfig)
    qa: QaConfig = field(default_factory=QaConfig)
    remote: RemoteConfig = field(default_factory=RemoteConfig)
    output: OutputConfig = field(default_factory=OutputConfig)


def _apply_section(obj, data: dict):
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
        for section_name in ("mineru", "convert", "qa", "remote", "output"):
            if section_name in data:
                _apply_section(getattr(cfg, section_name), data[section_name])
    return cfg
