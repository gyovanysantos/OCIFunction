# CI/CD & Collaborative Git Workflow Guide

> **Portable playbook** — Copy this file into any new project and adapt the workflow files to match.

---

## Table of Contents

1. [Core Concepts](#1-core-concepts)
2. [Git Collaborative Workflow](#2-git-collaborative-workflow)
3. [GitHub Actions — How CI/CD Works](#3-github-actions--how-cicd-works)
4. [Secrets Management](#4-secrets-management)
5. [Branch Protection Setup](#5-branch-protection-setup)
6. [Daily Workflow — Step by Step](#6-daily-workflow--step-by-step)
7. [Commit Message Convention](#7-commit-message-convention)
8. [Pull Request Best Practices](#8-pull-request-best-practices)
9. [Troubleshooting Common Issues](#9-troubleshooting-common-issues)
10. [Checklist for New Projects](#10-checklist-for-new-projects)

---

## 1. Core Concepts

### What is CI (Continuous Integration)?

Every time someone opens a Pull Request (PR), an automated pipeline runs to:
- **Install dependencies** (`npm ci`)
- **Type-check** the code (`tsc --noEmit`)
- **Build** the project (`npm run build`)
- **Run tests** (when you have them)

If any step fails, the PR gets a ❌ and **cannot be merged**. This catches bugs before they reach production.

### What is CD (Continuous Deployment)?

When a PR is merged into `main`, another pipeline automatically:
- **Builds a Docker image** from the latest code
- **Pushes it** to a container registry (OCIR, Docker Hub, etc.)
- **Deploys** the new image to the production server
- **Verifies** the deployment with a health check

**The golden rule:** `main` branch = production. It must always be deployable.

### Why Pull Requests?

Without PRs, developers push directly to `main`. This leads to:
- Broken builds in production
- No record of *why* a change was made
- No chance for others to catch bugs before they go live

With PRs:
- Every change is **reviewed** before merging
- CI pipeline **validates** the code automatically
- You get a **history** of what changed and why
- Team members **learn from each other** by reading PRs

---

## 2. Git Collaborative Workflow

### The Branching Model

```
main (production — always deployable)
  │
  ├── feature/add-new-tool        ← your work happens here
  ├── fix/api-timeout-error       ← bug fixes here
  ├── chore/update-dependencies   ← maintenance here
  └── docs/update-readme          ← documentation here
```

**Rules:**
1. **Never push directly to `main`** — always go through a PR
2. **One feature = one branch = one PR** — keep changes small and focused
3. **Delete branches after merging** — keep the repo clean
4. **Sync with `main` regularly** — avoid large merge conflicts

### Branch Naming Convention

| Prefix | Use For | Example |
|--------|---------|---------|
| `feature/` | New features or capabilities | `feature/add-item-search` |
| `fix/` | Bug fixes | `fix/token-refresh-timeout` |
| `chore/` | Maintenance, dependencies, config | `chore/upgrade-node-22` |
| `docs/` | Documentation changes only | `docs/update-api-reference` |
| `ci/` | CI/CD pipeline changes | `ci/add-deploy-step` |

---

## 3. GitHub Actions — How CI/CD Works

### Terminology

| Term | What It Is | Analogy |
|------|-----------|---------|
| **Workflow** | A `.yml` file in `.github/workflows/` | A recipe |
| **Trigger** | What starts the workflow (`push`, `pull_request`) | "Start cooking when the oven preheats" |
| **Job** | A group of steps that run on one machine | A course in the meal |
| **Step** | A single command or action inside a job | One instruction in the recipe |
| **Action** | A reusable step published by the community | A pre-made sauce from the store |
| **Runner** | The machine that executes the workflow | The kitchen |
| **Artifact** | A file produced by the workflow (logs, builds) | The finished dish |

### Anatomy of a Workflow File

```yaml
# .github/workflows/ci.yml

name: CI                           # Display name on GitHub

on:                                # TRIGGERS — when does this run?
  pull_request:                    # On any PR targeting these branches:
    branches: [main]
  push:                            # On direct push to these branches:
    branches: [main]

jobs:                              # JOBS — what work to do
  build:                           # Job name (you choose this)
    runs-on: ubuntu-latest         # RUNNER — which machine type

    steps:                         # STEPS — sequential commands
      - uses: actions/checkout@v4          # ACTION — checkout the code
      - uses: actions/setup-node@v4        # ACTION — install Node.js
        with:
          node-version: 22
      - run: npm ci                        # COMMAND — install deps
      - run: npm run build                 # COMMAND — build project
```

### How Triggers Work

| Trigger | When It Fires | Use Case |
|---------|--------------|----------|
| `pull_request` → `main` | PR opened, updated, or reopened | CI — validate before merge |
| `push` → `main` | Code pushed/merged to main | CD — deploy to production |
| `workflow_dispatch` | Manual button click on GitHub | Emergency deploys |

### This Project's Pipelines

**CI Pipeline (`.github/workflows/ci.yml`):**
```
PR opened → Install deps → Type-check → Build → ✅ or ❌
```

**CD Pipeline (`.github/workflows/deploy.yml`):**
```
Merged to main → Build Docker image → Push to OCIR → Restart Container → Health check
```

---

## 4. Secrets Management

**NEVER put credentials in code.** GitHub Secrets are encrypted environment variables available to workflows.

### How to Add Secrets

1. Go to your repo on GitHub
2. **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Enter the name (e.g., `OCI_AUTH_TOKEN`) and value
5. Click **Add secret**

### Secrets for This Project

| Secret Name | What It Is | Where to Get It |
|-------------|-----------|-----------------|
| `OCI_AUTH_TOKEN` | OCIR authentication token | OCI Console → User Settings → Auth Tokens |
| `OCI_TENANCY_NAMESPACE` | Your tenancy's object storage namespace | OCI Console → Tenancy Details |
| `OCI_REGION` | OCI region identifier | e.g., `sa-saopaulo-1` |
| `OCI_COMPARTMENT_ID` | Target compartment OCID | OCI Console → Compartment |
| `OCI_CONTAINER_INSTANCE_ID` | Container Instance OCID | OCI Console → Container Instances |
| `OCI_USER_OCID` | Your user OCID | OCI Console → User Settings |
| `OCI_FINGERPRINT` | API key fingerprint | OCI Console → API Keys |
| `OCI_PRIVATE_KEY` | PEM-encoded private key (base64) | Your local `~/.oci/oci_api_key.pem` |
| `JDE_AIS_URL` | AIS REST endpoint | Your JDE admin |
| `JDE_USERNAME` | JDE service account username | Your JDE admin |
| `JDE_PASSWORD` | JDE service account password | Your JDE admin |

### Using Secrets in Workflows

```yaml
env:
  JDE_AIS_URL: ${{ secrets.JDE_AIS_URL }}

steps:
  - run: echo "Deploying to ${{ secrets.OCI_REGION }}"
```

**Important:** Secrets are masked in logs — GitHub replaces them with `***`.

---

## 5. Branch Protection Setup

Branch protection ensures no one (including you) can push directly to `main`.

### Step-by-Step Setup

1. Go to your repo on GitHub
2. **Settings** → **Branches**
3. Click **Add branch protection rule** (or **Add classic branch protection rule**)
4. Set **Branch name pattern** to: `main`
5. Enable these settings:

| Setting | Value | Why |
|---------|-------|-----|
| Require a pull request before merging | ✅ On | Forces PR workflow |
| Require approvals | 1 | At least one teammate reviews |
| Require status checks to pass | ✅ On | CI must pass before merge |
| Require branches to be up to date | ✅ On | No stale merges |
| Do not allow bypassing | ✅ On | Even admins follow the rules |
| Allow force pushes | ❌ Off | Prevents history rewriting |
| Allow deletions | ❌ Off | Can't delete main |

6. Under "Require status checks", search and select: **`build`** (this is the CI job name)
7. Click **Create** / **Save changes**

---

## 6. Daily Workflow — Step by Step

### Starting New Work

```bash
# 1. Make sure you're on main and up-to-date
git checkout main
git pull origin main

# 2. Create a feature branch
git checkout -b feature/add-item-search

# 3. Do your work... edit files, test locally
npm run build       # make sure it compiles
npm run dev         # test locally

# 4. Stage and commit your changes
git add .
git commit -m "feat: add item search tool with F4101 lookup"

# 5. Push your branch to GitHub
git push -u origin feature/add-item-search
# (-u sets the upstream — only needed on first push of a branch)
```

### Opening a Pull Request

1. Go to your repo on GitHub
2. You'll see a yellow banner: *"feature/add-item-search had recent pushes"*
3. Click **Compare & pull request**
4. Fill in the PR template (What changed, Why, How to test)
5. Assign a reviewer (or CODEOWNERS auto-assigns one)
6. Click **Create pull request**
7. Wait for CI to pass ✅
8. Reviewer approves → Click **Merge pull request** → **Confirm merge**

### After Merging

```bash
# Switch back to main and pull the merged changes
git checkout main
git pull origin main

# Delete your local branch (it's merged, you don't need it)
git branch -d feature/add-item-search

# Start next feature
git checkout -b feature/next-thing
```

### Handling Merge Conflicts

If GitHub says "This branch has conflicts", it means someone else changed the same lines you did.

```bash
# 1. On your feature branch, pull the latest main
git checkout feature/add-item-search
git pull origin main

# 2. Git will show conflict markers in files:
#    <<<<<<< HEAD
#    your changes
#    =======
#    their changes
#    >>>>>>> main

# 3. Edit the files to resolve conflicts (keep what's correct)

# 4. Stage the resolved files and commit
git add .
git commit -m "chore: resolve merge conflicts with main"

# 5. Push the updated branch
git push origin feature/add-item-search
```

### Syncing Your Branch with Main (Preventive)

Do this regularly to avoid big conflicts:

```bash
git checkout feature/my-feature
git pull origin main
# Resolve any conflicts if they appear
git push origin feature/my-feature
```

---

## 7. Commit Message Convention

Use the **Conventional Commits** format: `type: short description`

| Type | When to Use | Example |
|------|------------|---------|
| `feat` | New feature or capability | `feat: add customer lookup tool` |
| `fix` | Bug fix | `fix: handle expired AIS token gracefully` |
| `chore` | Maintenance, deps, config | `chore: upgrade typescript to 5.7` |
| `docs` | Documentation only | `docs: update setup instructions` |
| `ci` | CI/CD pipeline changes | `ci: add deploy job to workflow` |
| `refactor` | Code change (no new feature, no fix) | `refactor: extract AIS filter builder` |
| `test` | Adding or fixing tests | `test: add unit tests for orch-mapper` |
| `style` | Formatting, semicolons, etc. | `style: fix indentation in domain.ts` |

**Rules:**
- Keep the first line under 72 characters
- Use present tense: "add feature" not "added feature"
- Use imperative mood: "fix bug" not "fixes bug"
- No period at the end

**Multi-line commits** (for larger changes):
```bash
git commit -m "feat: add batch order creation endpoint

- Accepts array of order items
- Validates all items before creating
- Returns created order numbers

Closes #42"
```

---

## 8. Pull Request Best Practices

### The Golden Rules

1. **Small PRs** — Under 400 lines of changes. If it's bigger, split it up.
2. **One concern per PR** — Don't mix a bug fix with a new feature.
3. **Descriptive title** — The PR title becomes the merge commit message.
4. **Fill in the template** — Future-you will thank present-you.
5. **Self-review first** — Read your own diff on GitHub before requesting review.
6. **Respond to feedback** — Address all comments, don't just dismiss them.

### Reviewing Others' PRs

When you review a teammate's PR:

1. **Read the description** — Understand *what* and *why* before looking at code
2. **Run it locally** (if needed) — `git fetch origin && git checkout pr-branch`
3. **Focus on:**
   - Does it do what it claims?
   - Can I understand the code without extra explanation?
   - Are there edge cases not handled?
   - Are credentials or secrets exposed?
4. **Use constructive language** — "Consider using X here because..." not "This is wrong"
5. **Approve or request changes** — Don't leave PRs hanging

---

## 9. Troubleshooting Common Issues

### CI Failed — How to Debug

1. Go to the PR on GitHub
2. Click the ❌ **Details** link next to the failed check
3. Read the logs — the error is usually near the bottom
4. Common causes:
   - **TypeScript error** — fix the type error locally then push
   - **Missing dependency** — run `npm install` and commit `package-lock.json`
   - **Build script error** — test `npm run build` locally first

### "Can't push to main"

This is **expected** after branch protection is set up. You need to:
1. Create a branch: `git checkout -b feature/my-fix`
2. Push the branch: `git push origin feature/my-fix`
3. Open a PR on GitHub

### "Branch is out of date"

GitHub is telling you `main` changed since you branched off.

```bash
git pull origin main
# Resolve conflicts if any
git push origin feature/my-branch
```

### "Merge conflict"

See [Handling Merge Conflicts](#handling-merge-conflicts) above.

### Docker Build Fails in CD

1. Go to Actions tab on GitHub → click the failed run
2. Check the "Build and push Docker image" step logs
3. Common causes:
   - Dockerfile references a file not in the repo (check `.dockerignore`)
   - `npm ci` fails — your `package-lock.json` might be out of sync
   - Fix: run `npm install` locally, commit the updated `package-lock.json`

---

## 10. Checklist for New Projects

When setting up CI/CD on a new project, follow this checklist:

- [ ] **Repository created** on GitHub (private recommended)
- [ ] **`.gitignore`** — excludes `node_modules/`, `dist/`, `.env`, credentials
- [ ] **`.env.example`** — documents required env vars without values
- [ ] **`package.json` scripts** — includes `build`, `typecheck`, `ci`, `test`
- [ ] **`.github/workflows/ci.yml`** — CI pipeline for PRs
- [ ] **`.github/workflows/deploy.yml`** — CD pipeline for merges to main
- [ ] **`.github/pull_request_template.md`** — PR description template
- [ ] **`.github/CODEOWNERS`** — auto-assign reviewers
- [ ] **GitHub Secrets** — all credentials stored as secrets
- [ ] **Branch protection** — enabled on `main` with required checks
- [ ] **README badge** — shows CI/CD status
- [ ] **First PR** — test the whole workflow end to end

---

## Quick Reference Card

```bash
# === STARTING NEW WORK ===
git checkout main && git pull origin main
git checkout -b feature/my-feature

# === COMMITTING ===
git add .
git commit -m "feat: describe what you did"

# === PUSHING & PR ===
git push -u origin feature/my-feature
# → Open PR on GitHub → Wait for CI ✅ → Get review → Merge

# === AFTER MERGE ===
git checkout main && git pull origin main
git branch -d feature/my-feature

# === STAYING IN SYNC ===
git pull origin main              # on your feature branch

# === OOPS, UNDO LAST COMMIT (not pushed yet) ===
git reset --soft HEAD~1           # keeps your changes staged

# === SEE WHAT'S GOING ON ===
git status                        # what files changed
git log --oneline -10             # last 10 commits
git branch -a                     # all branches (local + remote)
git diff                          # see unstaged changes
```
