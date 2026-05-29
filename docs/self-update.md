# `ait self-update`

Built-in updater for the standalone binary.

## Usage

```bash
ait self-update            # interactive
ait self-update --yes      # no prompt
ait self-update --check    # check only, don't download
ait self-update --force    # update even if already at latest
ait self-update --json     # machine-readable output for agents
```

## Behavior by install method

`ait self-update` first detects how the binary was installed:

| Method | Behavior |
|---|---|
| Brew | Refuses with `"Run \`brew upgrade ait\` instead."` exit 1 |
| pip | Refuses with `"Run \`pip install --upgrade ait-vcs\` instead."` exit 1 |
| Standalone binary | Runs the update flow below |

## Update flow

1. Read current version from the binary's embedded `__version__`.
2. Query `api.github.com/repos/m24927605/ait/releases/latest`. Cached
   for 1 hour at `$XDG_STATE_HOME/ait/self_update_cache.json`.
3. Compare. If current ≥ latest, exit 0 ("Already at latest").
4. Show the update plan. Prompt `[Y/n]` unless `--yes`.
5. Check that the install dir is writable. If not, print a sudo hint
   and exit 1 *before* downloading.
6. Download the platform-specific binary and the release's
   `checksums.txt`.
7. Verify SHA256.
8. Atomic-replace via `mkstemp` + `os.replace` (POSIX same-filesystem).

## Failure modes

- **Network failure** → exit 1, original binary untouched.
- **Checksum mismatch** → exit 1, original binary untouched.
- **Permission denied** → exit 1 *before* the download, sudo hint
  printed.
- **`sys.frozen` not set** (e.g. running from pip) → refuses with the
  pip upgrade hint.

## Self-replace safety

POSIX allows `unlink`/`replace` of a currently-executing binary. The
running process holds the inode of the old binary; the new file lives
at a new inode. The currently-running `ait self-update` completes
normally; the next invocation picks up the new binary. Linux and
macOS both safe. Windows is not supported.
