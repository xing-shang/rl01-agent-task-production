FROM python:3.12-slim

RUN useradd -m -u 1000 agent

# ① node/npm is required by claude CLI; Chinese fonts and LibreOffice support
# deliverable rendering and validation.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl git bash jq ripgrep unzip nodejs npm \
        libreoffice-calc libreoffice-writer fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

# ② Pin Claude Code 2.1.114. The verifier container uses it for the judge.
RUN command -v claude >/dev/null 2>&1 \
      || npm install -g @anthropic-ai/claude-code@2.1.114; \
    command -v claude >/dev/null 2>&1 \
    && mkdir -p /root/.local/bin \
    && ln -sf "$(which claude)" /root/.local/bin/claude \
    && claude --version

# ③ RewardKit and common document parsers.
RUN pip install --no-cache-dir \
        "harbor-rewardkit[all]==0.1.7" markitdown \
        openpyxl pandas python-docx pypdf python-pptx PyYAML chardet matplotlib

# ④ Task-specific execution-side dependencies; use an empty file if none.
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY input_files/ /app/input_files/
RUN chown -R root:root /app/input_files && chmod -R a-w /app/input_files

RUN mkdir -p /app/output && chown -R agent:agent /app/output

WORKDIR /app
