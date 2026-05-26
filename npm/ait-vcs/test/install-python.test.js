"use strict";

const assert = require("node:assert/strict");
const { spawnSync } = require("node:child_process");
const path = require("node:path");
const test = require("node:test");

const installer = require("../scripts/install-python.js");
const wrapper = require("../bin/ait.js");

test("parseVersion reads Python semantic versions", () => {
  assert.deepEqual(installer.parseVersion("3.14.0\n"), [3, 14, 0]);
  assert.equal(installer.parseVersion("not python"), null);
});

test("supportsPython requires Python 3.14 or newer", () => {
  assert.equal(installer.supportsPython([3, 13, 9]), false);
  assert.equal(installer.supportsPython([3, 14, 0]), true);
  assert.equal(installer.supportsPython([3, 15, 0]), true);
  assert.equal(installer.supportsPython([4, 0, 0]), true);
});

test("venv and wrapper paths stay inside the npm package", () => {
  const root = path.resolve(__dirname, "..");
  assert.equal(installer.venvPython(root).startsWith(path.join(root, "libexec", "venv")), true);
  assert.equal(wrapper.aitExecutable(root).startsWith(path.join(root, "libexec", "venv")), true);
});

test("test_npm_installer_reports_missing_python_actionably", () => {
  assert.equal(installer.findPython(["definitely-not-python-3-14"]), null);
  const message = installer.missingPythonMessage();
  assert.match(message, /Python 3\.14\+/);
  assert.match(message, /Install Python 3\.14\+/);
  assert.match(message, /AIT_PYTHON=\/path\/to\/python3\.14/);
  assert.match(message, /npm rebuild -g ait-vcs/);
});

test("test_npm_pack_contains_expected_files", () => {
  const root = path.resolve(__dirname, "..");
  const result = spawnSync("npm", ["pack", "--dry-run", "--json"], {
    cwd: root,
    encoding: "utf8",
  });
  assert.equal(result.status, 0, result.stderr);
  const payload = JSON.parse(result.stdout);
  const files = new Set(payload[0].files.map((item) => item.path));
  assert.equal(files.has("package.json"), true);
  assert.equal(files.has("README.md"), true);
  assert.equal(files.has("bin/ait.js"), true);
  assert.equal(files.has("scripts/install-python.js"), true);
  assert.equal([...files].some((item) => item.startsWith("test/")), false);
  assert.equal([...files].some((item) => item.startsWith(".git")), false);
  assert.equal([...files].some((item) => item.startsWith("libexec/")), false);
});
