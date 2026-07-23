"""pdf2wiki — convert technical books (native-text PDFs) into clean, chapter-split,
LLM-ready Markdown, built on a dual-pass MinerU pipeline.

Pipeline stages:
  1. convert  — MinerU pipeline pass (embedded text layer, byte-perfect code) merged with a
                MinerU hybrid/VLM pass (correct table grids, Mermaid diagram transcription).
  2. phase5   — post-processing chain: caption unbleed -> code-fence language retag ->
                dash normalize -> mermaid repair -> code unescape -> chapter split with
                YAML frontmatter.
  3. qa       — reproducible page sampling + per-page review artifacts for manual back-checks.
  4. batch    — manifest-driven multi-book runs, resumable, with optional SSH remote execution.
"""

__version__ = "0.2.3"
