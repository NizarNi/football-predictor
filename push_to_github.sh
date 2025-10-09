#!/bin/bash

echo "🚀 Football Predictor - GitHub Push Helper"
echo "=========================================="
echo ""

# Check if git is initialized
if [ ! -d .git ]; then
    echo "📦 Initializing Git repository..."
    git init
fi

# Prompt for GitHub repository URL
echo "📝 Please enter your GitHub repository URL:"
echo "   Example: https://github.com/yourusername/football-prediction-analyzer.git"
read -p "Repository URL: " REPO_URL

if [ -z "$REPO_URL" ]; then
    echo "❌ Error: Repository URL cannot be empty"
    exit 1
fi

# Remove existing remote if it exists
git remote remove origin 2>/dev/null

# Add new remote
echo "🔗 Adding GitHub remote..."
git remote add origin "$REPO_URL"

# Add all files
echo "📦 Staging all files..."
git add .

# Create commit
echo "💾 Creating commit..."
git commit -m "Initial commit: Football Prediction Platform

Features:
- Odds-based predictions from 30+ bookmakers
- Arbitrage detection and best odds display
- xG analytics from FBref
- Elo ratings from ClubElo.com
- Hybrid prediction model (60% Elo, 40% Market)
- Value bet detection
- Dark mode with localStorage persistence
- Responsive UI with Bootstrap 5.3
- Interactive xG trend charts

Tech Stack:
- Backend: Flask, Gunicorn, The Odds API
- Frontend: Bootstrap 5.3, Chart.js 4.4.0
- Analytics: soccerdata, understat, ClubElo API"

# Set main branch
git branch -M main

# Push to GitHub
echo "🚀 Pushing to GitHub..."
echo ""
echo "⚠️  You will be prompted for credentials:"
echo "   Username: Your GitHub username"
echo "   Password: Use a Personal Access Token (NOT your password)"
echo ""
echo "   To create a token: GitHub → Settings → Developer settings → Personal access tokens"
echo "   Required scope: 'repo' (full control)"
echo ""

git push -u origin main

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Successfully pushed to GitHub!"
    echo "🌐 View your repository at: $REPO_URL"
    echo ""
    echo "📋 Next steps:"
    echo "   1. Go to your GitHub repository"
    echo "   2. Add a description and topics (see GITHUB_SETUP.md)"
    echo "   3. Set up GitHub Actions for CI/CD (optional)"
    echo "   4. Deploy to Heroku, Vercel, or Railway (optional)"
else
    echo ""
    echo "❌ Push failed. Common issues:"
    echo "   1. Invalid Personal Access Token"
    echo "   2. Repository doesn't exist or you don't have access"
    echo "   3. Network connectivity issues"
    echo ""
    echo "📖 See GITHUB_SETUP.md for detailed troubleshooting"
fi
