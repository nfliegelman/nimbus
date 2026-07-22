# Project instructions for Claude Code

Nimbus is a paper-trading forecast model for Kalshi daily temperature markets. It
runs unattended on GitHub Actions four times a day, prices market ladders from a
multi-provider weather ensemble, freezes simulated plays, settles them against
Kalshi's own results, and learns bias and spread corrections from those
settlements.

Its value is not the code. Its value is an unbroken, honestly measured track
record. Code can be rewritten in an afternoon. The record cannot be recreated at
any price. Every rule below exists to protect it.

## Read before editing

1. `HANDOFF.md` in full. Section 0b is the handback protocol, section 7b is the
   state schema contract, section 10 is the checkpoint protocol, plus the
   Decision Log and Changelog at the bottom.
2. `FUTURE.md`, especially the checkpoint 2 docket and the pre-registered gates.
3. `README.md`.
4. `audit/AUDIT_TODO.md` when audit findings are relevant. Note the path: this
   file lives in `audit/`, not at the repository root, and some documents still
   refer to it as if it were at root.
5. `protocols/` for the adoption and remediation protocols when a session is
   executing one of them.

## Absolute prohibitions

These are not preferences. A session that violates one has damaged the project
whether or not anything looks broken afterward.

1. **Never run `kalshi_weather.py` inside the working tree.** The script mutates
   `weather_state.json`: it resolves settlements, freezes plays, and rewrites
   `docs/`. Running it locally freezes plays against a local clock and a partial
   market snapshot, and if that state is ever committed the track record is
   silently corrupted. To run it, copy the repository to a scratch directory,
   delete the copy's `.git`, and run it there:

   ```
   rm -rf /tmp/nimbus-sbx && cp -r . /tmp/nimbus-sbx && cd /tmp/nimbus-sbx \
     && rm -rf .git && CI=true python3 kalshi_weather.py
   ```

2. **Never delete, regenerate, normalize, reformat, reorder, truncate, or
   `.gitignore` `weather_state.json`.** It is live state, deliberately committed
   by the scheduled workflow. It is large and machine-written, so it will look
   generated. It is not. There is no `.gitignore` in this repository; do not add
   one that excludes state files.

3. **Never `git push --force`, never `git reset --hard`, never `git checkout .`
   without first checking whether the cron has committed.** The workflow pushes
   to `main` several times a day. Force-pushing can destroy state commits that
   exist nowhere else. Always `git pull --rebase origin main` immediately before
   pushing.

4. **Never hand-edit anything in `docs/`.** That directory is regenerated
   GitHub Pages output, written by the script and committed by the cron. Never
   include it in a handback. Never place source or protocol documents there.

5. **Never weaken a model, settlement, calibration, cap, gate, or evaluation
   guard to make a test, a lint rule, or a CI job pass.** If a guard blocks a
   change, the change is wrong, not the guard.

6. **Never amend a kill criterion, a money gate, or a pre-registered
   experimental gate without explicit owner approval quoted verbatim in the
   Decision Log.** Governance is not editable by the party it constrains. A
   general expression of trust is not approval for a specific amendment.

## Measurement discipline

- **Any change to forecasting, pricing, or play-selection behavior requires a
  `MODEL_VERSION` bump, a Changelog entry, and a Decision Log row in the same
  commit.** Era comparability depends entirely on `MODEL_VERSION` splitting eras
  correctly. A behavior change shipped without a bump corrupts every
  before-and-after comparison in the project, invisibly, for weeks.

- **One knob family per commit.** Never ship two behavior changes together. If
  results move afterward, the cause must be attributable to exactly one change.

- **A refactor that claims to preserve behavior must prove it.** Run the sandbox
  procedure above on the code before and after, then diff the generated
  `docs/index.html` and `docs/results.html` and the resulting state delta. Claim
  equivalence only after seeing it.

- **Never tune by scanning result tables for the worst-looking or
  best-looking cell.** Experiments are registered in `FUTURE.md` with their
  gates, thresholds, and remedies fixed in writing before the deciding data
  exists. When a gate fires, execute the pre-committed action; do not
  relitigate the threshold because the number came in smaller than hoped, and do
  not extend a gate because the result was disappointing.

- **Small samples do not license action.** Losing streaks in a pre-registered
  experimental cell are the cost of buying a verdict, not evidence to act on
  before the gate fills.

## Validation required before any commit touching code

1. `python3 -m py_compile kalshi_weather.py`
2. `python3 test_nimbus.py` (currently 23 tests; all must pass, and new
   behavior needs a new test)
3. Sandbox double-run per the procedure above: run the script twice, confirm it
   completes, confirm no unintended plays freeze, and confirm any new display
   renders.
4. `grep -rn $'\u2014' --include='*.py' --include='*.md' --include='*.yml' .`
   must return nothing. Zero em dashes repository-wide is a hard convention.

## Commit and push protocol

- Stage only the files the session deliberately edited. Never stage
  `weather_state.json` or `docs/` unless the task is explicitly about them.
- `git pull --rebase origin main` immediately before every push, so a
  concurrent cron commit is never clobbered.
- Commit code and its documentation together: `HANDOFF.md` changelog, Decision
  Log row, and any `FUTURE.md` status change belong in the same commit as the
  code they describe.

## Workflow separation

`.github/workflows/run.yml` is the operational workflow. It runs the model,
writes state, and commits it, on four crons: 12:17, 16:10, 21:38, and 02:07 UTC.
The 16:10 run is shadow-only via `NIMBUS_SHADOW_RUN`. It legitimately holds
`contents: write`.

Any validation or CI workflow added later must be a separate file with
`permissions: contents: read`. It must never run the model against live state,
settle records, or receive write access.

## Recovery

Every version of the state file is in git history (roughly 69 commits and
counting). If state is ever damaged:

```
git log --oneline -- weather_state.json
git checkout <good-commit-sha> -- weather_state.json
```

Verify the restored file parses and its `resolved` count is plausible before
committing. Recovery is straightforward as long as history has not been
rewritten, which is why the force-push prohibition above is absolute.
