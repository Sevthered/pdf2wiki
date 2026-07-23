# Security Policy

## Supported versions

pdf2wiki is in **alpha (0.x)**. Only the latest published release on PyPI receives security fixes;
there are no long-term support branches.

| Version        | Supported |
|----------------|-----------|
| latest `0.2.x` | ✅        |
| anything older | ❌        |

## Reporting a vulnerability

Please report security issues **privately** — do **not** open a public issue.

Use GitHub's private vulnerability reporting: the repository's **Security** tab →
**Report a vulnerability**. That opens a private advisory visible only to the maintainer.

You can expect an acknowledgement within about **7 days**. If a fix is warranted, it ships in the
next patch release, and the advisory is published once users have had a chance to upgrade.

## Scope notes

- **Data egress:** in `--mineru-cloud` mode pdf2wiki uploads the source PDF to the third-party
  mineru.net service. This is behind an explicit opt-in flag and is logged loudly; do not use it for
  material you cannot send off-site. See the cloud how-to in `docs/`.
- **External process:** pdf2wiki drives the MinerU CLI as a subprocess. Vulnerabilities in MinerU
  itself should be reported to that project; report here anything about how pdf2wiki *invokes* it
  (argument handling, path/quoting, remote execution over SSH).
- **Releases** are published via PyPI Trusted Publishing (OIDC, no stored token) and carry PEP 740
  provenance attestations — verify them on the PyPI file page.
