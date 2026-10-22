import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { test } from 'node:test';
import { runClaudeJudge } from './decreen-judge-claude.mjs';

const verdict = sourceId => ({
  sourceId, result: 'cannot-judge', classification: 'MODEL-GAP',
  rationale: 'Evidence is insufficient.', evidence: [], inspectedFiles: [],
});

function fixture(run) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'decreen-claude-adapter-'));
  const env = {
    DECREEN_JUDGE_AGENT_TOKEN: 'fake-oauth-token',
    DECREEN_JUDGE_BUNDLE: path.join(dir, 'bundle.json'),
    DECREEN_JUDGE_PROMPT: path.join(dir, 'prompt.txt'),
    DECREEN_JUDGE_VERDICTS: path.join(dir, 'output', 'verdicts.json'),
    ANTHROPIC_API_KEY: 'must-not-be-used', ANTHROPIC_AUTH_TOKEN: 'must-not-be-used',
  };
  fs.writeFileSync(env.DECREEN_JUDGE_BUNDLE, JSON.stringify({ laws: [{ sourceId: 'LAW-1' }, { sourceId: 'LAW-2' }] }));
  fs.writeFileSync(env.DECREEN_JUDGE_PROMPT, 'Evaluate the prepared bundle.');
  try { run(env); }
  finally { fs.rmSync(dir, { recursive: true, force: true }); }
}

test('host writes complete structured verdicts without allowing the model to write files', () => {
  fixture(env => {
    runClaudeJudge({ env, run: (_command, args, options) => {
      assert.equal(options.input, 'Evaluate the prepared bundle.');
      assert.equal(options.env.CLAUDE_CODE_OAUTH_TOKEN, env.DECREEN_JUDGE_AGENT_TOKEN);
      assert.equal(options.env.ANTHROPIC_API_KEY, undefined);
      assert.equal(options.env.ANTHROPIC_AUTH_TOKEN, undefined);
      assert.ok(args.includes('--safe-mode'));
      assert.ok(!args.includes('--bare'));
      assert.equal(args[args.indexOf('--tools') + 1], 'Read,Glob,Grep,Bash');
      const schema = JSON.parse(args[args.indexOf('--json-schema') + 1]);
      assert.deepEqual(schema.properties.verdicts.items.properties.sourceId.enum, ['LAW-1', 'LAW-2']);
      return { status: 0, stdout: JSON.stringify({ subtype: 'success', is_error: false,
        structured_output: { verdicts: [verdict('LAW-2'), verdict('LAW-1')] } }) };
    } });
    const payload = JSON.parse(fs.readFileSync(env.DECREEN_JUDGE_VERDICTS, 'utf8'));
    assert.deepEqual(payload.verdicts.map(item => item.sourceId), ['LAW-2', 'LAW-1']);
  });
});

test('fails before writing when Claude errors, refuses, or returns no structured response', () => {
  for (const response of [
    { status: 1, stdout: '' },
    { status: null, error: { code: 'ETIMEDOUT' } },
    { status: 0, stdout: 'not JSON' },
    { status: 0, stdout: 'null' },
    { status: 0, stdout: JSON.stringify({ is_error: true, subtype: 'error_during_execution' }) },
    { status: 0, stdout: JSON.stringify({ subtype: 'error_max_turns', is_error: false }) },
    { status: 0, stdout: JSON.stringify({ subtype: 'success', result: 'I could not write the file.' }) },
    { status: 0, stdout: JSON.stringify({ subtype: 'success', structured_output: { verdicts: [] } }) },
  ]) fixture(env => {
    assert.throws(() => runClaudeJudge({ env, run: () => response }), /no verdicts written/);
    assert.equal(fs.existsSync(env.DECREEN_JUDGE_VERDICTS), false);
  });
});

test('rejects missing, duplicate, unknown, or malformed verdicts', () => {
  for (const verdicts of [
    [verdict('LAW-1')],
    [verdict('LAW-1'), verdict('LAW-1')],
    [verdict('LAW-1'), verdict('UNKNOWN')],
    [verdict('LAW-1'), { ...verdict('LAW-2'), rationale: ' ' }],
    [verdict('LAW-1'), { ...verdict('LAW-2'), classification: 'APPROVED' }],
    [verdict('LAW-1'), { ...verdict('LAW-2'), result: 'passed' }],
    [verdict('LAW-1'), { ...verdict('LAW-2'), evidence: [{}] }],
    [verdict('LAW-1'), { ...verdict('LAW-2'), inspectedFiles: 'backend/app/main.py' }],
    [verdict('LAW-1'), null],
  ]) fixture(env => {
    assert.throws(() => runClaudeJudge({ env, run: () => ({ status: 0,
      stdout: JSON.stringify({ subtype: 'success', structured_output: { verdicts } }),
    }) }), /no verdicts written/);
    assert.equal(fs.existsSync(env.DECREEN_JUDGE_VERDICTS), false);
  });
});

test('rejects missing credentials and invalid source IDs without invoking Claude', () => {
  fixture(env => {
    const run = () => { throw new Error('Claude should not run'); };
    assert.throws(() => runClaudeJudge({ env: { ...env, DECREEN_JUDGE_AGENT_TOKEN: '' }, run }), /Missing DECREEN_JUDGE_AGENT_TOKEN/);
    for (const laws of [[], [{ sourceId: '' }], [{ sourceId: 'LAW-1' }, { sourceId: 'LAW-1' }]]) {
      fs.writeFileSync(env.DECREEN_JUDGE_BUNDLE, JSON.stringify({ laws }));
      assert.throws(() => runClaudeJudge({ env, run }), /unique source IDs/);
    }
    assert.equal(fs.existsSync(env.DECREEN_JUDGE_VERDICTS), false);
  });
});
