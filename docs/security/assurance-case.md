# Security assurance case

This document is pdf2wiki's **assurance case**: a structured argument, backed by evidence in the
code, that the project handles untrusted input and its external boundaries safely. It states the
threat model, the trust boundaries, the input-validation approach, and a requirement→evidence table
mapping each security claim to the source that implements it.

It exists to satisfy the OpenSSF Best Practices *Silver* criteria `assurance_case`,
`input_validation`, `implement_secure_design`, and `documentation_security`, and to give a reviewer a
single place to check *how* the security-relevant code behaves. The vulnerability-reporting process
lives in [`SECURITY.md`](../../SECURITY.md); this document is the design-level companion to it.

Line references point at `main` and may drift by a few lines as the code evolves — the function names
(`_require_https`, `_safe_extract`, `_ssh_opts`, `_apply_section`) are the stable anchors.

## Scope and assets

pdf2wiki is a **command-line tool** run by its own operator on their own machine. It is not a network
service, has no users other than the operator, stores no credentials of third parties, and exposes no
listening port. The assets worth protecting are therefore modest and local:

- **The operator's filesystem** — pdf2wiki writes Markdown, images, and logs; a path-handling bug
  could let a crafted input write outside the intended output directory.
- **The operator's mineru.net API token** — used only in the opt-in cloud mode; must never leak to a
  log, a disk file, or an unencrypted connection.
- **The confidentiality of the source PDF** — in cloud mode the PDF is uploaded off-site; the operator
  must never be surprised into sending material off their machine.
- **The integrity of the conversion** — a silently dropped page or corrupted code block is a
  correctness failure the pipeline treats as security-adjacent (fail loud, never emit a silent gap).

## Trust boundaries

Four boundaries separate trusted pdf2wiki code from data or systems it does not control. Everything
crossing inward is treated as untrusted.

| # | Boundary | What crosses it | Why it is untrusted |
|---|----------|-----------------|---------------------|
| B1 | **Source PDF → parser** | Arbitrary PDF bytes chosen by the operator, possibly downloaded from the web | A malformed or hostile PDF can carry oversized structures, malformed text layers, or filenames engineered to influence downstream paths |
| B2 | **MinerU subprocess** | The MinerU CLI and its vLLM/torch workers, invoked as a child process | Third-party code with a large native dependency surface; its output (`content_list`, image files) is parsed by pdf2wiki |
| B3 | **mineru.net cloud API** | HTTP requests/responses, a presigned upload URL, and a result ZIP, over the network | A remote service outside the operator's control; the ZIP contents and any server-supplied URLs are attacker-influenceable |
| B4 | **Remote GPU host (SSH)** | Commands sent to, and files pulled from, a remote converter host | The remote shell interprets everything sent to it; unquoted paths or a hijacked channel could execute unintended commands |

## Threat model and mitigations

### B1 — Untrusted PDF input

*Threats:* path traversal via crafted embedded filenames; resource exhaustion from a pathological PDF;
malformed structures crashing the parser.

*Mitigations:* pdf2wiki writes conversion output only under a caller-supplied output root and derives
image filenames deterministically rather than trusting embedded names. Parsing failures surface as a
loud, named error (the [zero-fail scrape](../explanation/design-principles.md#zero-fail-scrape)
coverage gate hard-stops rather than emit a book with a silently dropped page). MinerU's stderr is
captured, never suppressed, so a failing pass names its page range and log path.

### B2 — MinerU subprocess

*Threats:* shell injection through a filename or option; an orphaned GPU worker after a timeout;
a swallowed traceback hiding a failure.

*Mitigations:* every subprocess is invoked in **list form with no `shell=True`**, so arguments are
passed as an `argv` vector and are never re-parsed by a shell (`executor.py:93` `_run`;
`merge.py:223` `Popen`). The local MinerU pass runs with `start_new_session=True` so a timeout can
`SIGKILL` the **whole process group** rather than orphan a VRAM-pinning worker (`merge.py`). Timeouts
bound every pass; a `TimeoutExpired` becomes a typed failure, not a hang.

### B3 — mineru.net cloud egress

*Threats:* the API token or PDF travelling over an unencrypted connection; a token leaking into logs;
a **zip-slip** result archive overwriting arbitrary files; a surprise upload of confidential material;
following an attacker-supplied non-HTTPS URL (SSRF-adjacent).

*Mitigations:*

- **HTTPS is enforced** on every outbound URL before any token or PDF is sent — the API base, the
  presigned upload URL, and the result-download URL each pass through `_require_https`
  (`cloud.py:64`), which refuses any scheme other than `https` (`cloud.py:70`). Call sites:
  `cloud.py:183` (upload), `:229` (API base), `:308` (download).
- **The token is never logged or written to disk.** It is resolved from config → `MINERU_API_TOKEN`
  env → an operator-managed token file, env preferred (`_resolve_token`, `cloud.py:130`), sent only in
  an `Authorization: Bearer` header over TLS, and any URL is passed through `_redact_url`
  (`cloud.py:54`) — which strips the query string — before it is logged.
- **Zip-slip is blocked.** The result ZIP is extracted by `_safe_extract` (`cloud.py:79`), which
  resolves each member's real path and rejects any member that does not stay within the destination
  directory (`cloud.py:87`) *before* calling `extractall`.
- **Egress is opt-in and loud.** Cloud mode requires the explicit `--mineru-cloud` (or
  `--cloud-model merge`) flag and logs the upload prominently; the token file is git-ignored. See the
  [cloud how-to](../how-to/convert-in-the-cloud.md) and the data-egress note in `SECURITY.md`.

### B4 — Remote GPU host over SSH

*Threats:* command injection through an unquoted path in a remote command line; an interactive
auth/host-key prompt hanging a batch; a silently truncated file pull.

*Mitigations:* every path interpolated into a remote command is `shlex.quote`-d
(`executor.py:123-125` convert, `:148-156` fetch). SSH runs with `BatchMode=yes` (no interactive
prompt) and bounded connect/keepalive timeouts (`_ssh_opts`, `executor.py:74`), so a dead or
prompting host fails fast instead of hanging mid-batch. Every `scp` is timeout-checked, so a partial
pull fails loudly rather than producing a truncated file. See
[set up a remote GPU](../how-to/set-up-remote-gpu.md).

## Input-validation map

pdf2wiki follows an **allowlist / fail-closed** stance at each point where external data enters:

| Input | Validation | Where |
|-------|-----------|-------|
| Outbound URLs (API base, upload, download) | scheme allowlist — **`https` only**, else refuse | `cloud.py:64` `_require_https` |
| mineru.net result ZIP members | realpath must stay within the destination dir, else refuse to extract | `cloud.py:79` `_safe_extract` |
| Subprocess arguments (MinerU, ssh, scp) | passed as an `argv` list, never a shell string (`shell=True` is never used) | `executor.py:93`, `merge.py:223` |
| Remote shell paths | `shlex.quote` on every interpolated path | `executor.py:123-156` |
| Config file keys | only fields declared on the dataclass are applied; unknown keys are ignored, not `eval`-d | `config.py:118` `_apply_section` |
| MinerU binary path | resolved on `PATH` or from an explicit config value, `FileNotFoundError` if absent | `config.py:36` `resolve_binary` |
| Page range | typed integers in the MinerU config section (0-based `-s`/`-e`) | `config.py` |
| API token | required non-empty; sourced env-first, never echoed | `cloud.py:130` `_resolve_token` |

## Secure-design practices (`implement_secure_design`)

- **Least privilege / minimal attack surface** — no listening service, no elevated privileges, no
  persistent daemon. The tool does one thing and exits.
- **Fail closed and fail loud** — HTTPS refusal, zip-slip refusal, the coverage gate, and captured
  subprocess stderr all prefer a loud, named failure over a silent unsafe result.
- **Secrets out of band** — the API token is never a committed value; it lives in an env var or a
  git-ignored file and is redacted from all logging.
- **Opt-in egress** — nothing leaves the operator's machine without an explicit flag.
- **Signed, provenanced releases** — releases publish via PyPI Trusted Publishing (OIDC, no stored
  token) with PEP 740 provenance attestations (see `SECURITY.md` and the release runbook).

## Requirement → evidence

| OpenSSF Silver criterion | How pdf2wiki meets it | Evidence |
|--------------------------|-----------------------|----------|
| `assurance_case` | This document — threat model, trust boundaries, mitigations | this file |
| `input_validation` | Allowlist/fail-closed at every external input | the input-validation map above; `cloud.py`, `executor.py`, `config.py` |
| `implement_secure_design` | Least privilege, fail-closed, secrets out of band, opt-in egress | the secure-design section above |
| `documentation_security` | Reporting process + design-level assurance case | `SECURITY.md` + this file |
| `vulnerability_response_process` | Private GitHub reporting, ~7-day acknowledgement, fix in next patch | [`SECURITY.md`](../../SECURITY.md) |

## Residual risks and assumptions

- **MinerU and its ML stack are trusted third-party code.** pdf2wiki hardens *how it invokes* MinerU
  (argv, timeouts, group-kill) but does not sandbox it; a vulnerability inside MinerU itself is out of
  scope and should be reported upstream.
- **mineru.net is a third-party service** hosting user PDFs off-site under policies pdf2wiki cannot
  audit. The mitigation is informed opt-in, not technical containment — do not upload material you
  cannot send off your machine.
- **The operator's SSH configuration is trusted.** pdf2wiki relies on the operator's known-hosts and
  key setup; it does not manage host-key trust on their behalf.
- **Single-maintainer project.** Review depth is bounded by one maintainer (see `GOVERNANCE.md`);
  the automated CI (ruff, `mypy --strict`, pytest, golden snapshots) is the compensating control.
