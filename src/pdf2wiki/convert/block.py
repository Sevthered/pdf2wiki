"""Typed view over one MinerU/merge content block.

A block is a `content_list.json` record (plus pdf2wiki-injected keys). It is modelled as a thin,
raw-dict-backed adapter rather than a field dataclass on purpose:

- **Byte-identical `blocks.json`.** The backing store IS the dict that evolves in place today, so
  `to_dict()` returns exactly what `json.dump` wrote before — the golden snapshot stays unchanged.
- **We don't own MinerU's schema.** Only the ~21 keys pdf2wiki actually reads/writes get typed
  accessors; unmodelled MinerU keys ride along untouched in `raw` (no drift/lies about their schema).
- **Incremental migration.** Consumers can switch from `b["k"]` to `b.k` slice by slice while blocks
  still round-trip to dicts at the seams (parse boundary in, `blocks.json`/`render` out).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class Block:
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Block:
        return cls(raw=d)

    def to_dict(self) -> dict[str, Any]:
        return self.raw

    def copy(self) -> Block:
        return Block(raw=dict(self.raw))

    # ---- MinerU-owned keys pdf2wiki reads/writes ----
    @property
    def type(self) -> str:
        return str(self.raw.get("type", ""))

    @property
    def sub_type(self) -> str:
        return str(self.raw.get("sub_type", "") or "")

    @sub_type.setter
    def sub_type(self, v: str | None) -> None:
        self.raw["sub_type"] = v

    @property
    def bbox(self) -> list[float] | None:
        v = self.raw.get("bbox")
        if isinstance(v, str):
            v = json.loads(v)
        return [float(x) for x in v] if v else None

    @property
    def page_idx(self) -> int:
        return int(self.raw.get("page_idx", 0))

    @property
    def text(self) -> str | None:
        return self.raw.get("text")

    @text.setter
    def text(self, v: str) -> None:
        self.raw["text"] = v

    @property
    def text_level(self) -> int | None:
        return self.raw.get("text_level")

    @property
    def code_body(self) -> str:
        return str(self.raw.get("code_body", "") or "")

    @code_body.setter
    def code_body(self, v: str) -> None:
        self.raw["code_body"] = v

    @property
    def table_body(self) -> str | None:
        return self.raw.get("table_body")

    @table_body.setter
    def table_body(self, v: str | None) -> None:
        self.raw["table_body"] = v

    @property
    def content(self) -> str:
        return str(self.raw.get("content", "") or "")

    @content.setter
    def content(self, v: str) -> None:
        self.raw["content"] = v

    @property
    def img_path(self) -> str | None:
        return self.raw.get("img_path")

    @property
    def image_caption(self) -> list[Any]:
        return self.raw.get("image_caption") or []

    @property
    def table_caption(self) -> list[Any]:
        return self.raw.get("table_caption") or []

    @property
    def chart_caption(self) -> list[Any]:
        return self.raw.get("chart_caption") or []

    @property
    def list_items(self) -> list[Any]:
        return self.raw.get("list_items") or []

    # ---- pdf2wiki-injected keys ----
    @property
    def abs_page(self) -> int:
        return int(self.raw.get("abs_page", 0))

    @abs_page.setter
    def abs_page(self, v: int) -> None:
        self.raw["abs_page"] = v

    @property
    def imgdir(self) -> str | None:
        return self.raw.get("_imgdir")

    @imgdir.setter
    def imgdir(self, v: str) -> None:
        self.raw["_imgdir"] = v

    @property
    def src(self) -> str | None:
        return self.raw.get("_src")

    @src.setter
    def src(self, v: str) -> None:
        self.raw["_src"] = v

    @property
    def code_flag(self) -> bool:
        return bool(self.raw.get("_code_flag", False))

    @code_flag.setter
    def code_flag(self, v: bool) -> None:
        self.raw["_code_flag"] = v

    @property
    def indent_flag(self) -> bool:
        return bool(self.raw.get("_indent_flag", False))

    @indent_flag.setter
    def indent_flag(self, v: bool) -> None:
        self.raw["_indent_flag"] = v

    @property
    def reindented(self) -> bool:
        return bool(self.raw.get("_reindented", False))

    @reindented.setter
    def reindented(self, v: bool) -> None:
        self.raw["_reindented"] = v

    @property
    def code_path(self) -> Literal["verified", "flagged", "pipeline_only"] | None:
        return self.raw.get("_code_path")

    @code_path.setter
    def code_path(self, v: Literal["verified", "flagged", "pipeline_only"]) -> None:
        self.raw["_code_path"] = v
