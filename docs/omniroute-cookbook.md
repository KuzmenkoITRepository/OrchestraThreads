# OmniRoute Cookbook

## Overview

OrchestraThreads uses **OmniRoute** for LLM inference routing.

- **OmniRoute**: Provider management, OAuth, API key storage, model routing

## Architecture

```
Agent → OmniRoute (service URL: http://orchestra-omniroute:20128) → LLM Provider
```

## Quick Start

### 1. Start Services

```bash
docker compose up -d orchestra-omniroute
```

### 2. Log In and Configure Providers

Open OmniRoute UI: http://localhost:20229

Use the `OMNIROUTE_INITIAL_PASSWORD` value printed by the deploy/provision scripts.

The OrchestraThreads deploy flow now auto-creates the runtime API key and stores it as `OMNIROUTE_API_KEY` in Vault.
You do **not** need to create the runtime API key manually anymore.

Add your providers:

- **Codex**: OAuth or API key
- **Anthropic (Claude)**: API key
- **OpenAI**: API key
- **Minimax**: API key
- **Qwen**: API key

### 3. Test Connection

```bash
curl -X POST http://localhost:20229/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "codex/gpt-5.4-mini",
    "messages": [{"role": "user", "content": "Hello"}],
    "max_tokens": 50
  }'
```

## Agent Configuration

### Manifest Setup

In your agent's `manifest.yaml`:

```yaml
runtime:
  env:
    OMNIROUTE_URL: http://orchestra-omniroute:20128
    OMNIROUTE_API_KEY: ${OMNIROUTE_API_KEY}
```

### Model Selection

Use provider-prefixed model names:

```yaml
backend:
  config:
    model: codex/gpt-5.4-mini
    # or
    model: kiro/claude-haiku-4.5
    # or
    model: minimax/MiniMax-M2.7
```

## Available Models

Query available models:

```bash
curl http://localhost:20229/v1/models | jq '.data[] | .id'
```

Common models:

- `codex/gpt-5.4-mini` - Fast Codex model
- `codex/gpt-5.4` - Full Codex model
- `kiro/claude-haiku-4.5` - Fast Claude
- `kiro/claude-sonnet-4.5` - Full Claude
- `minimax/MiniMax-M2.7` - Minimax model

## Storage

OmniRoute stores data in `.omniroute/`:

```
.omniroute/
├── data/           # OmniRoute database and config
```

This directory is gitignored and contains:

- Provider credentials
- API keys
- OAuth tokens
- Call logs

**Never commit `.omniroute/` to git.**

## Troubleshooting

### Check Service Health

```bash
# OmniRoute
curl http://localhost:20229/health
```

### Provider Not Working

1. Check OmniRoute UI for provider status
2. Verify API key/OAuth token is valid
3. Check logs:

   ```bash
   docker logs orchestra-omniroute --tail 100
   ```

### Model Not Found

Use provider prefix:

- ❌ `gpt-5.4` (ambiguous)
- ✅ `codex/gpt-5.4` (explicit)

### No Credentials Error

```json
{"error": {"message": "No credentials for provider: anthropic"}}
```

**Solution**: Add provider credentials in OmniRoute UI (http://localhost:20229)

## Advanced Configuration

### Custom Routing

OmniRoute supports:

- Load balancing across multiple accounts
- Fallback providers
- Rate limiting
- Cost tracking

Configure in OmniRoute UI → Settings → Routing

### Environment Variables

```yaml
# docker-compose.yml
orchestra-omniroute:
  environment:
    PORT: 20128
    HOSTNAME: 0.0.0.0
    INITIAL_PASSWORD: your-secure-password
```

## Migration to OmniRoute defaults

If updating existing agents:

1. Update agent manifests:
   ```yaml
   # Current runtime contract
   OMNIROUTE_URL: http://orchestra-omniroute:20128
   OMNIROUTE_API_KEY: ${OMNIROUTE_API_KEY}
   ```

2. Configure providers in OmniRoute UI

3. Restart agents:
   ```bash
   curl -X POST http://localhost:8790/api/v1/registry/reload
   curl -X POST http://localhost:8790/api/v1/agents/{slug}/restart
   ```

## Best Practices

1. **Use specific model names**: Always include provider prefix
2. **Monitor costs**: Check OmniRoute UI for usage stats
3. **Backup credentials**: Export provider config from OmniRoute UI
4. **Test before production**: Verify each provider works before deploying

## References

- OmniRoute: https://github.com/diegosouzapw/omniroute
- OpenAI API Spec: https://platform.openai.com/docs/api-reference
