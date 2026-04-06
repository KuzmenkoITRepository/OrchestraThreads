# OmniRoute + WET Cookbook

## Overview

OrchestraThreads uses **OmniRoute** + **WET** for LLM inference routing. This replaces the deprecated `llm-proxy` service.

- **OmniRoute**: Provider management, OAuth, API key storage, model routing
- **WET**: OpenAI-compatible proxy that routes requests through OmniRoute

## Architecture

```
Agent → WET (port 8100) → OmniRoute (port 20129) → LLM Provider
```

## Quick Start

### 1. Start Services

```bash
docker compose up -d orchestra-omniroute orchestra-wet
```

### 2. Configure Providers

Open OmniRoute UI: http://localhost:20129

Default password: `CHANGEME`

Add your providers:
- **Codex**: OAuth or API key
- **Anthropic (Claude)**: API key
- **OpenAI**: API key
- **Minimax**: API key
- **Qwen**: API key

### 3. Test Connection

```bash
curl -X POST http://localhost:8101/v1/chat/completions \
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
    LLM_PROXY_URL: http://orchestra-wet:8100
    LLM_PROXY_ENABLED: "true"
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
curl http://localhost:20129/v1/models | jq '.data[] | .id'
```

Common models:
- `codex/gpt-5.4-mini` - Fast Codex model
- `codex/gpt-5.4` - Full Codex model
- `kiro/claude-haiku-4.5` - Fast Claude
- `kiro/claude-sonnet-4.5` - Full Claude
- `minimax/MiniMax-M2.7` - Minimax model

## Storage

OmniRoute and WET store data in `.omniroute/`:

```
.omniroute/
├── data/           # OmniRoute database and config
└── wet/            # WET session data
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
curl http://localhost:20129/health

# WET
docker logs orchestra-wet --tail 50
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

**Solution**: Add provider credentials in OmniRoute UI (http://localhost:20129)

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
    OMNIROUTE_PORT: 20129
    INITIAL_PASSWORD: your-secure-password

orchestra-wet:
  environment:
    WET_UPSTREAM: http://orchestra-omniroute:20129
```

## Migration from llm-proxy

If migrating from the old `llm-proxy`:

1. Update agent manifests:
   ```yaml
   # Old
   LLM_PROXY_URL: http://llm-proxy:8787

   # New
   LLM_PROXY_URL: http://orchestra-wet:8100
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
5. **Keep WET internal**: Only expose OmniRoute UI externally if needed

## References

- OmniRoute: https://github.com/diegosouzapw/omniroute
- WET Proxy: https://github.com/dzhng/wet
- OpenAI API Spec: https://platform.openai.com/docs/api-reference
