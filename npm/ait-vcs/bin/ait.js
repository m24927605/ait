#!/usr/bin/env node
"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { spawn } = require("node:child_process");

function packageRoot() {
  return path.resolve(__dirname, "..");
}

function aitExecutable(root = packageRoot()) {
  if (process.platform === "win32") {
    return path.join(root, "libexec", "venv", "Scripts", "ait.exe");
  }
  return path.join(root, "libexec", "venv", "bin", "ait");
}

function main() {
  const command = aitExecutable();
  if (!fs.existsSync(command)) {
    console.error(
      [
        "ait-vcs npm install did not finish installing the Python CLI.",
        "",
        "Fix:",
        "  npm rebuild -g ait-vcs",
        "",
        "Requirements:",
        "  Python 3.14+ must be available as python3.14, python3, or python.",
      ].join("\n"),
    );
    process.exit(1);
  }

  const child = spawn(command, process.argv.slice(2), { stdio: "inherit" });
  child.on("error", (error) => {
    console.error(`failed to start ait: ${error.message}`);
    process.exit(1);
  });
  child.on("exit", (code, signal) => {
    if (signal) {
      process.kill(process.pid, signal);
      return;
    }
    process.exit(code ?? 1);
  });
}

if (require.main === module) {
  main();
}

module.exports = { aitExecutable };
