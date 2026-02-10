# Configure Carl AI Environment Variables

## Status

✅ **Deployment is live**: https://deeptrace.projectcivitas.com
✅ **Carl AI integration code**: Deployed
⏳ **Environment variables**: Need to be configured

---

## Configure via Cloudflare Dashboard

### Step 1: Navigate to Settings

1. Go to: https://dash.cloudflare.com/c19818aa9be140eeb372bb45da855919/workers/services/view/deeptrace/production/settings
2. Scroll down to **Environment variables**

### Step 2: Add Carl AI Variables

Click **Add variable** twice and configure:

**Variable 1:**
- **Variable name**: `CARL_API_URL`
- **Value**: `https://ai.baytides.org/api/generate`
- **Type**: Text (not Secret - it's just a URL)

**Variable 2:**
- **Variable name**: `CARL_DEFAULT_MODEL`
- **Value**: `qwen2.5:3b-instruct`
- **Type**: Text

### Step 3: Save and Redeploy

1. Click **Save**
2. A new deployment will trigger automatically
3. Wait 1-2 minutes for redeployment

---

## Configure via Wrangler CLI (Alternative)

If you prefer using CLI:

```bash
# Navigate to your project
cd /Users/steven/Github/DeepTrace

# Add Carl API URL
wrangler pages secret put CARL_API_URL --project-name=deeptrace
# When prompted, enter: https://ai.baytides.org/api/generate

# Add default model
wrangler pages secret put CARL_DEFAULT_MODEL --project-name=deeptrace
# When prompted, enter: qwen2.5:3b-instruct
```

**Note**: For Pages, these aren't really "secrets" but wrangler treats all env vars as secrets for Pages projects.

---

## Verify Configuration

After adding the variables:

```bash
# Check that the variables are set (won't show values for security)
wrangler pages deployment list --project-name=deeptrace
```

Or visit the Cloudflare dashboard and verify the variables appear under **Environment variables**.

---

## Test Carl AI Integration

Once configured, you can test the integration:

1. Visit: https://deeptrace.projectcivitas.com
2. Create a test case
3. Add evidence items
4. Click **"Analyze with Carl"** (when UI is implemented)

Or test the API directly:

```bash
curl -X POST https://deeptrace.projectcivitas.com/api/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "What investigative approaches should be considered for a cold case with limited physical evidence?",
    "mode": "default"
  }'
```

---

## GitHub Actions Secret

For automated deployments via GitHub Actions, you also need to add the Cloudflare API token to GitHub secrets:

1. Go to: https://github.com/baytides/DeepTrace/settings/secrets/actions
2. Click **New repository secret**
3. Name: `CLOUDFLARE_API_TOKEN`
4. Value: Your Cloudflare API token (from Cloudflare dashboard → My Profile → API Tokens)

This enables the GitHub Actions workflow to deploy automatically on push.

---

## Next Steps

After configuration is complete:

1. ✅ Environment variables set
2. ✅ New deployment triggered
3. 🎯 **Phase 2**: Add Carl AI UI to dashboard
   - "Analyze with Carl" buttons on evidence/hypothesis pages
   - Mode selector dropdown
   - Display analysis results
   - Link to Langfuse for observability

DeepTrace is now fully integrated with your Carl AI infrastructure! 🚀
