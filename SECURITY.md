# Security Policy

## Supported versions

pdf2wiki is in **alpha (0.x)**. Only the latest published release on PyPI receives security fixes;
there are no long-term support branches.

| Version        | Supported |
|----------------|-----------|
| latest `0.2.x` | ✅        |
| anything older | ❌        |

**Scope and duration of support.** Support covers **security fixes only** (not backported features). A
release is supported from the moment it is published **until the next release supersedes it**; at that
point the older version reaches **end-of-life and no longer receives security updates**. Upgrading is a
single `pip install --upgrade pdf2wiki`. This policy will be revisited once the project reaches a
stable `1.0`.

## Reporting a vulnerability

Please report security issues **privately** — do **not** open a public issue.

Use GitHub's private vulnerability reporting: the repository's **Security** tab →
**Report a vulnerability**. That opens a private advisory visible only to the maintainer.

You can expect an acknowledgement within about **7 days**. If a fix is warranted, it ships in the
next patch release, and the advisory is published once users have had a chance to upgrade.

Reporters are **credited** in the published advisory and release notes (unless you ask to remain
anonymous). GitHub Security Advisories records reporter credit automatically.

## Scope notes

- **Data egress:** in `--mineru-cloud` mode pdf2wiki uploads the source PDF to the third-party
  mineru.net service. This is behind an explicit opt-in flag and is logged loudly; do not use it for
  material you cannot send off-site. See the cloud how-to in `docs/`.
- **External process:** pdf2wiki drives the MinerU CLI as a subprocess. Vulnerabilities in MinerU
  itself should be reported to that project; report here anything about how pdf2wiki *invokes* it
  (argument handling, path/quoting, remote execution over SSH).
- **Releases** are published via PyPI Trusted Publishing (OIDC, no stored token) and carry PEP 740
  provenance attestations — verify them on the PyPI file page. Release **version tags are
  cryptographically signed**; verify one with `git tag -v vX.Y.Z`.
- **Commits** are signed off under the [Developer Certificate of Origin](https://developercertificate.org/)
  (`Signed-off-by:` trailer) — see `CONTRIBUTING.md`.

## Secrets and credentials

The project uses very few secrets and manages them as follows (storage, access, rotation):

- **mineru.net API token** (optional `--mineru-cloud` mode, user-supplied): read from the
  `MINERU_API_TOKEN` environment variable or a user-managed token file; never committed (the
  token-bearing `pdf2wiki.toml` is git-ignored), never written to disk by the tool, and redacted from
  all logging. Rotate it at <https://mineru.net/apiManage/token> and update your env var / token file.
- **`CODECOV_TOKEN`** (CI coverage upload): stored only as a GitHub Actions **encrypted repository
  secret**, exposed to a single trusted CI step; rotate by regenerating it in Codecov and updating the
  GitHub secret.
- **PyPI publishing:** no stored token — releases use **Trusted Publishing** (OIDC), so there is no
  long-lived credential to leak or rotate.
- **SSH keys** (optional `--remote` mode): the operator's own OS-managed keys; pdf2wiki never stores or
  transmits them.

Repository secret hygiene is backed by GitHub **secret scanning with push protection**, which blocks a
push containing a detected secret.

## Assurance case

For the design-level security argument — threat model, trust boundaries, the input-validation map, and
a requirement→evidence table — see [`docs/security/assurance-case.md`](docs/security/assurance-case.md).

## Security Insights

Machine-readable security metadata (OpenSSF [Security Insights](https://github.com/ossf/security-insights-spec)
v2.2.0) — including the project's OSPS Baseline Level 1 self-attestation — is published at
[`security-insights.yml`](security-insights.yml).
