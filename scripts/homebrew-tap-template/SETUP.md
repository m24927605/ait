# Maintainer Setup — homebrew-ait

One-time setup. Required before the first release that ships binaries.

## 1. Create the tap repo

```bash
gh repo create m24927605/homebrew-ait --public \
    --description "Homebrew tap for ait" \
    --license MIT
```

## 2. Seed the tap repo from this template

From inside the main `ait` repo:

```bash
tmp=$(mktemp -d)
gh repo clone m24927605/homebrew-ait "$tmp/homebrew-ait"
cp -R scripts/homebrew-tap-template/Formula "$tmp/homebrew-ait/"
cp scripts/homebrew-tap-template/README.md "$tmp/homebrew-ait/"
cd "$tmp/homebrew-ait"
git add Formula README.md
git commit -m "initial tap seed"
git push
```

The placeholder SHA256s (all zeros) will be overwritten by the first
release of the binary pipeline.

## 3. Create the TAP_PUSH_TOKEN secret

Generate a fine-grained PAT scoped to write to `m24927605/homebrew-ait`
only:

```bash
gh auth refresh --scopes repo
# or visit https://github.com/settings/tokens?type=beta
```

Add the token as a secret in the main `ait` repo:

```bash
gh secret set TAP_PUSH_TOKEN --body "<paste-pat>" \
    -R m24927605/ait
```

## 4. Verify

Trigger a `workflow_dispatch` release-binary build to confirm CI can
build the binaries. Once that's clean, cut a real release tag to
exercise the full pipeline end-to-end (build + checksums + update-tap).
