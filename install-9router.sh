#!/bin/bash

###############################################################################
# Ubuntu 24.04
# Install Claude CLI + 9Router
###############################################################################

set -e

echo "Updating Ubuntu..."

sudo apt update

sudo apt -y upgrade

echo "Installing packages..."

sudo apt install -y \
git \
curl \
wget \
jq \
build-essential \
python3 \
python3-pip \
python3-venv \
unzip \
zip \
ca-certificates

###############################################################################
# Install NodeJS LTS
###############################################################################

curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -

sudo apt install -y nodejs

###############################################################################
# Update npm
###############################################################################

sudo npm install -g npm@latest

###############################################################################
# Claude CLI
###############################################################################

echo "Installing Claude CLI..."

npm install -g @anthropic-ai/claude-code

###############################################################################
# Git Clone 9Router
###############################################################################

mkdir -p ~/AI

cd ~/AI

if [ ! -d "9router" ]; then
git clone https://github.com/danielmiessler/9router.git
fi

cd 9router

###############################################################################
# Install
###############################################################################

npm install

###############################################################################
# Build
###############################################################################

npm run build || true

###############################################################################
# Config directory
###############################################################################

mkdir -p ~/.config/9router

###############################################################################
# Create config
###############################################################################

cat > ~/.config/9router/config.json <<EOF
{
  "default_provider":"anthropic",
  "providers":{
      "anthropic":{
          "apiKey":"",
          "model":"claude-opus-4"
      },
      "openai":{
          "apiKey":"",
          "model":"gpt-5"
      },
      "google":{
          "apiKey":"",
          "model":"gemini-2.5-pro"
      },
      "ollama":{
          "baseURL":"http://127.0.0.1:11434",
          "model":"llama3.1"
      }
  }
}
EOF

###############################################################################
# PATH
###############################################################################

grep -q 9router ~/.bashrc || echo 'export PATH=$PATH:$HOME/AI/9router/bin' >> ~/.bashrc

echo

echo "Installation Complete"

echo

echo "Edit"

echo "~/.config/9router/config.json"

echo

echo "Add your API Keys."

echo

echo "Run"

echo

echo "9router"
