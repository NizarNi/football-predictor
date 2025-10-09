# 🚀 GitHub Export Instructions

## Option 1: Download Archive (Simplest)

I've created a compressed archive with all your code:

**📦 Download File:** `football_predictor_export.tar.gz` (65KB)

### How to Use:
1. Look in the Replit file explorer for `football_predictor_export.tar.gz` in the root directory
2. Click on the file and select "Download"
3. Extract on your local machine:
   ```bash
   tar -xzf football_predictor_export.tar.gz
   ```

---

## Option 2: Push to GitHub (Recommended)

### Step 1: Create GitHub Repository

1. Go to https://github.com/new
2. Create a new repository named `football-prediction-analyzer`
3. Make it **Public** or **Private** (your choice)
4. **DO NOT** initialize with README, .gitignore, or license (we have those already)
5. Copy the repository URL (e.g., `https://github.com/yourusername/football-prediction-analyzer.git`)

### Step 2: Initialize Git in Replit

Open the Replit Shell and run these commands:

```bash
# Initialize git (if not already initialized)
git init

# Add all files
git add .

# Create first commit
git commit -m "Initial commit: Football Prediction Platform with xG analytics and Elo ratings"

# Add your GitHub repository as remote
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git

# Push to GitHub
git branch -M main
git push -u origin main
```

### Step 3: Authenticate with GitHub

When prompted for credentials:
- **Username**: Your GitHub username
- **Password**: Use a **Personal Access Token** (NOT your password)

#### To create a Personal Access Token:
1. Go to GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)
2. Click "Generate new token (classic)"
3. Give it a name: "Replit Football Predictor"
4. Select scopes: Check `repo` (full control of private repositories)
5. Click "Generate token"
6. **Copy the token** (you won't see it again!)
7. Use this token as your password when pushing

---

## Option 3: Use Replit's Git Integration

### Using Replit's Built-in Git Tools:

1. **Open Git Panel** in Replit (look for the Git icon in the sidebar)
2. **Stage all changes** by clicking the "+" button next to files
3. **Commit** with message: "Initial commit"
4. **Add Remote**: Click "Add remote" and paste your GitHub repo URL
5. **Push**: Click "Push" to send to GitHub

---

## 📋 What's Included in the Export

```
football_predictor/
├── 📄 app.py                    # Main Flask application (467 lines)
├── 📄 odds_api_client.py        # The Odds API integration (141 lines)
├── 📄 odds_calculator.py        # Predictions & arbitrage (263 lines)
├── 📄 xg_data_fetcher.py        # FBref xG statistics (700+ lines)
├── 📄 understat_client.py       # Understat integration (254 lines)
├── 📄 elo_client.py             # ClubElo ratings (339 lines)
├── 📄 requirements.txt          # Python dependencies
├── 📄 gunicorn_config.py        # Production config
├── 📄 README_EXPORT.md          # Complete documentation
├── 📁 templates/
│   └── 📄 index.html            # Complete UI (3,080 lines)
├── 📁 static/                   # Static assets
├── 📁 models/                   # (empty - for future use)
├── 📁 scraped_data/             # (gitignored)
└── 📁 processed_data/           # (gitignored)
```

Plus:
- ✅ `.gitignore` - Already configured
- ✅ `replit.md` - Project documentation
- ✅ `.replit` - Replit configuration

---

## 🔒 Important: Don't Commit API Keys!

Your API keys are stored as Replit secrets and are **NOT** included in the export. After cloning:

### Set Environment Variables:

**On Local Machine:**
```bash
export ODDS_API_KEY_1="your_key_1"
export ODDS_API_KEY_2="your_key_2"
export ODDS_API_KEY_3="your_key_3"
```

**On Heroku/Production:**
```bash
heroku config:set ODDS_API_KEY_1=your_key_1
heroku config:set ODDS_API_KEY_2=your_key_2
heroku config:set ODDS_API_KEY_3=your_key_3
```

**GitHub Secrets (for Actions):**
1. Go to repo → Settings → Secrets and variables → Actions
2. Add each key as a secret

---

## 🎯 Quick Clone & Run

Once pushed to GitHub, anyone can clone and run:

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/football-prediction-analyzer.git
cd football-prediction-analyzer

# Install dependencies
cd football_predictor
pip install -r requirements.txt

# Set environment variables
export ODDS_API_KEY_1="your_key"
export ODDS_API_KEY_2="your_key"
export ODDS_API_KEY_3="your_key"

# Run the app
python app.py
```

Open browser: `http://localhost:5000`

---

## 📝 Recommended GitHub Repo Description

**Description:**
> Football prediction platform with bookmaker odds analysis, arbitrage detection, xG analytics from FBref, Elo ratings, and hybrid prediction model. Features dark mode, responsive UI, and comprehensive betting insights.

**Topics:**
`football` `betting-analysis` `sports-analytics` `expected-goals` `xg-statistics` `arbitrage-detection` `elo-rating` `flask` `python` `data-visualization` `odds-comparison` `sports-betting` `fbref` `the-odds-api`

---

## ✅ Verification Checklist

After pushing to GitHub, verify:

- [ ] All code files are present
- [ ] `.gitignore` is working (no `__pycache__`, `.log` files)
- [ ] `README_EXPORT.md` is visible and formatted correctly
- [ ] No API keys or secrets are committed
- [ ] Repository is set to Public/Private as intended
- [ ] Dependencies in `requirements.txt` are complete

---

## 🆘 Troubleshooting

**Problem:** "Git is not initialized"
```bash
git init
```

**Problem:** "Remote already exists"
```bash
git remote remove origin
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
```

**Problem:** "Authentication failed"
- Use Personal Access Token instead of password
- Make sure token has `repo` scope

**Problem:** "Large files warning"
- Check if cache files are being committed
- Verify `.gitignore` is working: `git status`

---

## 📞 Need Help?

- GitHub Docs: https://docs.github.com/en/get-started/importing-your-projects-to-github/importing-source-code-to-github/adding-locally-hosted-code-to-github
- Replit Git Guide: https://docs.replit.com/programming-ide/using-git-on-replit

---

**Your export is ready! 🎉**
Choose the method that works best for you above.
