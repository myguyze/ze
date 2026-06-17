# ze-prospecting

Autonomous prospect research for Ze. Provides the `ProspectingAgent`, campaign store, browser-driven web research, and stale-campaign recovery.

## Role in Ze

Prospecting is Ze's autonomous outreach research mode. Given a target profile, the agent browses the web, gathers intelligence, drafts outreach messages, and tracks campaigns over multiple iterations — all without the user micromanaging each step.

### Key features

- `ProspectingAgent` — autonomous research loop with browser tools and outreach drafting
- `ProspectCampaignStore` — Postgres-backed campaign persistence across sessions
- Stale campaign recovery job — resumes or cleans up abandoned campaigns
- Server-driven UI components for campaign status and results

### Integration

Entry point `ze_prospecting`. Depends on `ze-browser` for web fetching and `ze-personal` for contact linking. Contributes the prospecting agent, campaign REST store, data domains for reset, and a proactive recovery job. Requires the browser sidecar running for web research.

```python
from ze_prospecting.plugin import ProspectingPlugin
```

## Responsibilities

| Module | What it provides |
|---|---|
| `agents/` | `ProspectingAgent`, research and outreach tools |
| `store.py` | `ProspectCampaignStore` — Postgres-backed campaign persistence |
| `jobs/campaigns.py` | `recover_stale_campaigns` — proactive recovery job |
| `types.py` | Campaign and prospecting settings types |
| `plugin.py` | `ProspectingPlugin(ZePlugin)` — registers agent, store, and job |

## Dependencies

```mermaid
graph LR
    prospecting[ze-prospecting] --> sdk[ze-sdk]
    prospecting --> browser[ze-browser]
    prospecting --> personal[ze-personal]
```

## Configuration

Prospecting settings in `config/config.yaml` under the `prospecting` key: `max_iterations`, `max_loop_tokens`, `stale_timeout_minutes`, `browser_delay_ms`, `browser_max_text_chars`.

## Testing

From the repo root:

```bash
make test-prospecting
```

See [docs/testing.md](../../docs/testing.md).
