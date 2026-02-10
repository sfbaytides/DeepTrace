# DeepTrace Deployment Notes

## Current Setup

✅ **Platform**: Cloudflare Pages
✅ **Deployment Method**: Direct GitHub integration (via Cloudflare dashboard)
✅ **Custom Domain**: `deeptrace.projectcivitas.com`
✅ **Status**: Live and working

---

## How Deployment Works

DeepTrace uses **Cloudflare Pages' direct GitHub integration**, configured in the Cloudflare dashboard:

1. You push code to `main` branch on GitHub (`baytides/DeepTrace`)
2. Cloudflare detects the push automatically
3. Cloudflare builds and deploys the site
4. Site is live at `deeptrace.projectcivitas.com`

**No GitHub Actions needed** - Cloudflare handles everything.

---

## Configuration

### Cloudflare Dashboard Settings

Project configured at:
https://dash.cloudflare.com/c19818aa9be140eeb372bb45da855919/workers/services/view/deeptrace

**Build Settings:**
- Build command: (empty - Cloudflare auto-detects Python)
- Build output directory: `.`
- Root directory: `/`

**Environment Variables (needed for Carl AI):**
- `CARL_API_URL` = `https://ai.baytides.org/api/generate`
- `CARL_DEFAULT_MODEL` = `qwen2.5:3b-instruct`
- `FLASK_ENV` = `production`
- `PYTHON_VERSION` = `3.11`

### wrangler.toml Configuration

The `wrangler.toml` file defines:
- D1 database binding: `deeptrace-db` (ID: `75b40646-51e2-4bda-be4e-36f849e4b23b`)
- R2 bucket binding: `deeptrace-files`
- Python version and environment variables

---

## Why GitHub Actions Was Removed

The `.github/workflows/deploy-cloudflare.yml` workflow was causing build failures:

```
Error: Project not found. The specified project name does not match any of your existing projects.
```

**Root cause**: When you connect a GitHub repo via the Cloudflare dashboard, Cloudflare creates and manages the project automatically. Using GitHub Actions with the `cloudflare/pages-action` would require creating the project via CLI/API first, which creates a conflict.

**Solution**: Since you already connected the repo in the dashboard, we removed the GitHub Actions workflow. Cloudflare's native integration is simpler and more reliable.

---

## Troubleshooting Build Failures

If builds fail in Cloudflare:

### 1. Check Build Logs

Visit: https://dash.cloudflare.com/c19818aa9be140eeb372bb45da855919/workers/services/view/deeptrace/production/builds

### 2. Common Issues

**"Python not found"**
- Ensure `PYTHON_VERSION=3.11` is set in environment variables
- Check that `requirements-web.txt` exists and is valid

**"Module not found"**
- Verify all dependencies are listed in `requirements-web.txt`
- Check for typos in import statements

**"Build command failed"**
- wrangler.toml has empty `[build]` section (correct for Pages)
- Cloudflare auto-detects Python and Flask

**"wrangler deploy error"**
- Ensure `[build]` section in wrangler.toml has:
  ```toml
  [build]
  command = ""
  cwd = ""
  ```
- This prevents Cloudflare from running Workers deploy command

### 3. Environment Variable Issues

If Carl AI doesn't work after deployment:
- Check that environment variables are set in Cloudflare dashboard
- Variables set in `wrangler.toml` under `[vars]` are NOT secrets
- Sensitive values (API keys) should be added via dashboard under "Environment variables"

---

## Manual Deployment (Optional)

If you ever need to deploy manually using Wrangler CLI:

```bash
# Install dependencies
cd /Users/steven/Github/DeepTrace
pip install -r requirements-web.txt

# Deploy directly (not recommended - use dashboard integration instead)
# wrangler pages deploy . --project-name=deeptrace

# Note: Manual deployment via Wrangler CLI is discouraged when using
# dashboard GitHub integration, as it can cause conflicts
```

**Recommended**: Always push to GitHub and let Cloudflare handle deployment automatically.

---

## Adding Environment Variables

### Via Cloudflare Dashboard

1. Go to: https://dash.cloudflare.com/c19818aa9be140eeb372bb45da855919/workers/services/view/deeptrace/production/settings
2. Scroll to **Environment variables**
3. Click **Add variable**
4. Enter name and value
5. Click **Save** (triggers automatic redeploy)

### Via Wrangler CLI

```bash
wrangler pages secret put VARIABLE_NAME --project-name=deeptrace
```

---

## Testing Deployment

After pushing to GitHub:

```bash
# Wait 2-3 minutes for build to complete, then:
curl -I https://deeptrace.projectcivitas.com

# Should return HTTP/2 200
```

---

## Production URLs

- **Primary**: https://deeptrace.projectcivitas.com
- **Cloudflare subdomain**: https://deeptrace-3nl.pages.dev (still works as backup)

---

## Carl AI Integration Status

✅ Code deployed (`src/deeptrace/ai_client.py`)
✅ Database schema updated (`ai_analyses` table)
⏳ Environment variables (need to be added via dashboard)
🎯 Phase 2: UI integration (coming next)

Once environment variables are configured, Carl AI will be fully operational.
