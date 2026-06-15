# Security Policy

## Scope

Ze is a self-hosted, single-user assistant with access to Gmail, Google Calendar, and arbitrary tool execution. Security issues in the following areas are in scope:

- Authentication bypass (WebSocket or REST)
- Privilege escalation or unauthenticated access to the API
- Prompt injection enabling unintended tool execution
- Credential or secret exposure (API keys, OAuth tokens)
- Dependency vulnerabilities with a credible exploit path

Issues with the React web client, deployment configuration, or third-party services (OpenRouter, Fly.io, ntfy) are generally out of scope unless they stem from Ze's own code.

## Reporting a vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Email: **joaoajmatos@proton.me**

Include:
- A description of the vulnerability and its impact
- Steps to reproduce (proof of concept if possible)
- The version or commit you tested against

## Responsible disclosure

Please give reasonable time to address the issue before public disclosure. Once a fix is released, you're welcome to publish a write-up — coordinating the timing is appreciated.

## Security model

Ze is **single-user by design**. There is no multi-tenant isolation. Before exposing your instance:

1. Generate a strong `ZE_API_KEY` — this is the sole gate for both REST and WebSocket access.
2. Keep `.env` out of version control; use `fly secrets` in production.
3. Review each agent's `capabilities` setting — prefer `confirm` or `draft_only` for write actions.
4. Use a non-guessable ntfy topic and set an access token.

Do not deploy Ze as a shared service without substantial hardening.
