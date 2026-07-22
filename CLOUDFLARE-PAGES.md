# Cloudflare Pages deployment

## Repository settings

Connect Cloudflare Pages to:

- Repository: `crhy/spaced`
- Production branch: `main`
- Framework preset: `None`
- Build command: `bash scripts/build-site.sh`
- Build output directory: `dist`

No environment variables are required.

## Custom domain

In the Cloudflare Pages project:

1. Open **Custom domains**.
2. Add `spacedlinux.com`.
3. Add `www.spacedlinux.com`.
4. Choose one as canonical and redirect the other with a Cloudflare Redirect Rule.

## Local preview

```bash
bash scripts/build-site.sh
python3 -m http.server 8080 --directory dist
```

Open `http://localhost:8080`.

## Suggested commit

```bash
git checkout -b website/cloudflare-redesign
git add README.md website/ scripts/build-site.sh
git commit -m "Redesign README and add Cloudflare Pages website"
git push -u origin website/cloudflare-redesign
```
