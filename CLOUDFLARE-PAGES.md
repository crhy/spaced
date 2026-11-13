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

## Publishing a release

Build and test the ISO first (`make release`, then the ISO smoke tests). Only then run:

```bash
scripts/website-release.sh publish
```

It copies the SHA-256 from `build/iso/spaced-linux-<version>-amd64.iso.sha256` into the marked download block of `website/index.html`; commit that file with the release. Merge to `main` only after the GitHub release `v<version>` exists with the ISO attached, because pushing to `main` deploys the site. While the ISO of `VERSION` is still unvalidated, keep the page honest with `scripts/website-release.sh preview`.
