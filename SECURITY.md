# Security Policy

## Supported versions

Epochix is pre-1.0. Only the latest minor release receives security fixes;
older versions are not patched.

| Version | Supported          |
|---------|--------------------|
| 0.3.x   | :white_check_mark: |
| < 0.3   | :x:                |

## Reporting a vulnerability

Please report security issues **privately** so we can land a fix before the
details are public.

1. Use GitHub's private vulnerability reporting: open
   <https://github.com/epochix/epochix/security/advisories/new>
   (nothing you type there is public).
2. Include a minimal reproduction (a log fragment, a curl, or a Python
   snippet) and the affected version. If you can't share a repro publicly,
   describe the data shape and we'll work with you.
3. We acknowledge within **3 business days** and aim to ship a fix within
   **30 days** for high-severity issues.

You will be credited in the release notes unless you ask to stay anonymous.

## Out of scope

- Findings against a server you have **explicitly exposed to the internet
  without** setting `EPOCHIX_AUTH_TOKEN`. The project ships secure-by-default
  (loopback bind, no `Access-Control-Allow-Origin`, docs hidden) — overriding
  those without auth is documented as unsafe and isn't a bug.
- Findings against the bundled demo logs or dev databases checked in for
  testing.
- Denial-of-service via supplying a multi-gigabyte log file to a local CLI.

## Hardening checklist for shared / hosted deployments

- Set `EPOCHIX_AUTH_TOKEN` to a long random secret.
- Set `EPOCHIX_CORS_ORIGINS` to your exact origin(s) (never `*` with
  credentials).
- Put the server behind a reverse proxy that terminates TLS and handles
  authentication for browser sessions.
- Mount the run database on a private volume; it isn't encrypted at rest.

See the README's *Security & deployment* section for the full reference.
