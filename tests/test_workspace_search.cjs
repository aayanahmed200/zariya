'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(
  path.join(__dirname, '..', 'webapp', 'static', 'workspace-search.js'),
  'utf8'
);
const isolatedWindow = {};
vm.runInNewContext(source, { window: isolatedWindow }, {
  filename: 'workspace-search.js',
  timeout: 1000
});

const search = isolatedWindow.ZariyaWorkspaceSearch;
assert.ok(search, 'search helper is exposed to the browser');
assert.equal(search.matchesAny(['Biology notes', 'cells'], 'BIOLOGY'), true,
  'Latin text search is case-insensitive');
assert.equal(search.matchesAny(['  Cell structure  '], '  cell  '), true,
  'queries are trimmed and content whitespace is ignored');
assert.equal(search.matchesAny(['Biology', 'Class notes'], 'revision'), false,
  'non-matching content is excluded');
assert.equal(search.matchesAny(['اردو کی مشق'], 'اردو'), true,
  'Urdu text can be searched');
assert.equal(search.matchesAny(['Ｂiology'], 'biology'), true,
  'Unicode compatibility forms are normalised');
assert.equal(search.matchesAny(['Flashcards', 'biology'], ''), true,
  'an empty query does not filter results');
assert.equal(search.matchesAny([], 'anything'), false,
  'empty content never matches a non-empty query');
assert.equal(search.matchesAny(['Physics'], '  '), true,
  'a whitespace-only query behaves like an empty query');

console.log('Workspace search tests passed');
