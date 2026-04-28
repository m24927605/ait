#!/usr/bin/env node
"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

const MINIMUM_PYTHON = [3, 14];

function packageRoot() {
  return path.resolve(__dirname, "..");
}

function venvPython(root = packageRoot()) {
  if (process.platform === "win32") {
    return path.join(root, "libexec", "venv", "Scripts", "python.exe");
  }
  return path.join(root, "libexec", "venv", "bin", "python");
}

function candidatePythons() {
  const candidates = [];
  for (const name of ["AIT_PYTHON", "PYTHON"]) {
    if (process.env[name]) candidates.push(process.env[name]);
  }
  candidates.push("python3.14", "python3", "python");
  return [...new Set(candidates)];
}

function parseVersion(text) {
  const match = text.trim().match(/^(\d+)\.(\d+)\.(\d+)/);
  if (!match) return null;
  return match.slice(1).map((item) => Number.parseInt(item, 10));
}

function supportsPython(version, minimum = MINIMUM_PYTHON) {
  if (!version) return false;
  if (version[0] !== minimum[0]) return version[0] > minimum[0];
  return version[1] >= minimum[1];
}

function pythonVersion(command) {
  const result = spawnSync(command, ["-c", "import platform; print(platform.python_version())"], {
    encoding: "utf8",
  });
  if (result.status !== 0) return null;
  return parseVersion(result.stdout);
}

function findPython() {
  for (const command of candidatePythons()) {
    const version = pythonVersion(command);
    if (supportsPython(version)) return command;
  }
  return null;
}

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    stdio: "inherit",
    ...options,
  });
  if (result.error) {
    throw result.error;
  }
  if (result.status !== 0) {
    throw new Error(`${command} ${args.join(" ")} failed with exit code ${result.status}`);
  }
}

function installSpec(root = packageRoot()) {
  if (process.env.AIT_NPM_PIP_SPEC) return process.env.AIT_NPM_PIP_SPEC;
  const pkg = JSON.parse(fs.readFileSync(path.join(root, "package.json"), "utf8"));
  return `ait-vcs==${pkg.version}`;
}

function install() {
  if (process.env.AIT_NPM_SKIP_POSTINSTALL === "1") {
    return;
  }

  const root = packageRoot();
  const python = findPython();
  if (!python) {
    throw new Error("ait-vcs requires Python 3.14+ on PATH as python3.14, python3, or python");
  }

  const venv = venvPython(root);
  if (!fs.existsSync(venv)) {
    run(python, ["-m", "venv", path.dirname(path.dirname(venv))]);
  }

  if (process.env.AIT_NPM_SKIP_PIP_UPGRADE !== "1") {
    run(venv, ["-m", "pip", "install", "--upgrade", "pip"]);
  }
  run(venv, ["-m", "pip", "install", "--upgrade", installSpec(root)]);
}

if (require.main === module) {
  try {
    install();
  } catch (error) {
    console.error(`ait-vcs postinstall failed: ${error.message}`);
    process.exit(1);
  }
}

module.exports = {
  MINIMUM_PYTHON,
  candidatePythons,
  findPython,
  installSpec,
  parseVersion,
  supportsPython,
  venvPython,
};
