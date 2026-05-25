#!/bin/bash
# =============================================================
# AI Software Delivery Room — GitHub Setup Script
# Run this once from inside the ai-software-delivery-room folder
# =============================================================
set -e

REPO_NAME="ai-software-delivery-room"
DESCRIPTION="Complete Claude Code skill + agentic SDLC harness. Strategic multi-agent room (11 agents) + Planner/Generator/Evaluator execution loop with contracts, JSON state, trace logs, teardown recovery, and risk-gated release."

echo ""
echo "=== AI Software Delivery Room — GitHub Setup ==="
echo ""

# Step 1: Git init and commit
echo "[1/4] Initializing git repository..."
git init
git branch -M main
git config user.name "Bilal Khan"
git config user.email "mbilaluddinkhan@gmail.com"
git add -A
git commit -m "feat: initial release of AI Software Delivery Room v1.1

Complete plug-and-play Claude Code skill + agentic SDLC harness.

Strategic Layer (11 agents):
- product-owner, business-analyst, solution-architect, ai-architect
- security-compliance, devops, critic, judge, documentation
- risk-manager, release-manager

Execution Layer (3 agents):
- planner — user-visible sprints only
- generator — negotiates acceptance contract + builds
- evaluator — adversarial QA, only role that can declare done

Slash Commands (6):
- /asdr, /longhorizon, /discover, /architect, /riskgate, /release

Harness Templates (8):
sprint contract, eval report, sprints.json, progress.json,
ADR template, risk register, agent output schema, decision log

Key principle: Generator builds. Evaluator passes/fails.
Risk Manager gates release. The AI cannot grade its own work."

echo "[1/4] ✓ Git commit created"

# Step 2: Create GitHub repo using gh CLI (if available) or curl
echo ""
echo "[2/4] Creating GitHub repository..."

if command -v gh &> /dev/null; then
    # Use GitHub CLI (preferred)
    gh repo create "$REPO_NAME" \
        --public \
        --description "$DESCRIPTION" \
        --source=. \
        --remote=origin \
        --push
    echo "[2/4] ✓ Repository created and pushed via GitHub CLI"
else
    echo ""
    echo "GitHub CLI (gh) not found. Using manual setup:"
    echo ""
    echo "  Option A — Install gh CLI first:"
    echo "    brew install gh"
    echo "    gh auth login"
    echo "    Then re-run this script."
    echo ""
    echo "  Option B — Create repo manually:"
    echo "    1. Go to https://github.com/new"
    echo "    2. Repository name: $REPO_NAME"
    echo "    3. Description: (paste below)"
    echo "       $DESCRIPTION"
    echo "    4. Set to Public"
    echo "    5. Do NOT initialize with README (we have one)"
    echo "    6. Click 'Create repository'"
    echo ""
    echo "  Then run these commands (replace YOUR_USERNAME):"
    echo ""
    echo "    git remote add origin https://github.com/YOUR_USERNAME/$REPO_NAME.git"
    echo "    git push -u origin main"
    echo ""
fi

echo ""
echo "=== Done! ==="
echo ""
echo "To use this in any new project:"
echo "  cp -R .claude /path/to/your-project/"
echo "  cp -R .harness /path/to/your-project/"
echo "  cp CLAUDE.md /path/to/your-project/"
echo ""
echo "Then in Claude Code:"
echo '  /asdr "Your software idea here"'
echo ""
