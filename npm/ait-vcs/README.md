# ait-vcs

`ait-vcs` is the npm installer for the `ait` command.

```bash
npm install -g ait-vcs
cd your-repo
ait init
claude ...
```

The npm package installs a private Python virtual environment and then
installs the matching PyPI package version of `ait-vcs`. The command
exported by npm is still `ait`.

Requirements:

- Node.js 18+
- Python 3.14+ available as `python3.14`, `python3`, or `python`
- Git

The npm package name is `ait-vcs` because `ait` is already owned by
another project on npm.
