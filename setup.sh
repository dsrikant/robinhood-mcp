#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==> Creating virtualenv..."
# Use the system Python (/usr/local/bin/python3) which has working SSL.
# pyenv's active Python (3.10.1) was compiled against openssl@1.1 which is no longer present.
/usr/local/bin/python3 -m venv "$SCRIPT_DIR/.venv"

echo "==> Installing dependencies..."
"$SCRIPT_DIR/.venv/bin/pip" install --quiet --upgrade pip
"$SCRIPT_DIR/.venv/bin/pip" install --quiet fastmcp "robin-stocks>=2.1"

echo "==> Creating ~/.robinhood/ directory..."
mkdir -p ~/.robinhood
chmod 700 ~/.robinhood

echo "==> Writing default config (if absent)..."
if [ ! -f ~/.robinhood/config.toml ]; then
  cat > ~/.robinhood/config.toml <<'EOF'
[safety]
max_order_value_usd = 5000.0
default_dry_run = true
confirmation_token_ttl_seconds = 60

[server]
log_level = "INFO"
log_file = "~/.robinhood/mcp.log"
EOF
  echo "    Wrote ~/.robinhood/config.toml"
else
  echo "    ~/.robinhood/config.toml already exists, skipping."
fi

PYTHON_BIN="$SCRIPT_DIR/.venv/bin/python"
SERVER_PATH="$SCRIPT_DIR/server.py"

echo ""
echo "==> Setup complete."
echo ""
echo "Add the following to ~/Library/Application Support/Claude/claude_desktop_config.json:"
echo ""
echo '{'
echo '  "mcpServers": {'
echo '    "robinhood": {'
echo "      \"command\": \"$PYTHON_BIN\","
echo "      \"args\": [\"$SERVER_PATH\"],"
echo '      "env": {'
echo '        "ROBINHOOD_USERNAME": "your@email.com",'
echo '        "ROBINHOOD_PASSWORD": "yourpassword"'
echo '      }'
echo '    }'
echo '  }'
echo '}'
echo ""
echo "Then restart Claude Desktop."
