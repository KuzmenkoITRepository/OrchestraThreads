FROM debian:bookworm-slim

# opencode is a self-contained binary; copy from host
COPY opencode /usr/local/bin/opencode
RUN chmod +x /usr/local/bin/opencode

# opencode needs git for project detection
RUN apt-get update && apt-get install -y --no-install-recommends \
    git ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

# Create isolated workspace and XDG dirs
RUN mkdir -p /workspace /opencode-config/opencode /opencode-data /opencode-cache /opencode-state \
    && git init /workspace

WORKDIR /workspace

# XDG isolation — each container gets its own config/data/cache
ENV XDG_CONFIG_HOME=/opencode-config
ENV XDG_DATA_HOME=/opencode-data
ENV XDG_CACHE_HOME=/opencode-cache
ENV XDG_STATE_HOME=/opencode-state

EXPOSE 4096

# Default: start opencode serve on 0.0.0.0:4096
CMD ["opencode", "serve", "--hostname", "0.0.0.0", "--port", "4096"]
