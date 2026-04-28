"use strict";

const assert = require("node:assert/strict");
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
