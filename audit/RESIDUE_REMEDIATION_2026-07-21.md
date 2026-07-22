# Investigation and Remediation Report

Generated-default ("AI residue") investigation and remediation, run 2026-07-21 against the Nimbus repository on branch `claude/ai-residue-remediation-bqpdp6`.

## Result
- Before residue score: 88 / 100 (low residue; already heavily audited)
- After residue score: 94 / 100
- Evidence confidence: High for the code and doc findings (line-verified and test-verified); Medium for the live-run layer (sandbox network policy blocked live API calls, see below)
- Research-completeness gate: PASSED for the layers touched; the deep stack-choice research was already done and recorded across the 12-batch audit and is not re-litigated here
- Build status: `python3 -m py_compile` clean on `kalshi_weather.py` and `test_nimbus.py`
- Test status: 24 / 24 passing (was 23; one regression test added)
- Deployment status: unchanged; `docs/` boards regenerate on the next scheduled Actions run
- Highest remaining risk: the retired "Brier below market" go-signal still appears in the AUTOMATION gate docs (FUTURE 6, FUTURE 1, LIVE_TRADING_SPEC gate 1). Left untouched on purpose because gate/kill criteria are never changed unilaterally; needs an explicit owner decision.

## Product truth
- Primary user: a single non-developer hobbyist owner who opens two static pages on an iPhone to see today's sized bets and a results tracker.
- Primary workflow: the bot runs unattended on GitHub Actions (three trading crons plus one shadow-only cron), scores Kalshi weather-temperature markets from a calibrated multi-model ensemble, sizes plays in units, and commits refreshed dashboards to GitHub Pages.
- Owner constraints: uploads files via the GitHub web UI at repo root, often phone-only; wants surgical, str-replace-verifiable edits. This is what makes the single-file, stdlib-only, root-level-handback design load-bearing rather than a default.
- Security/privacy boundary: repo is public for the paper phase (exposure is paper betting history only), mandatory-private before the first live order; no secrets in repo, state, or logs; stdlib-only is treated as a supply-chain security control inside a `contents:write` workflow.
- Key assumptions: no MODEL_VERSION or pricing behavior may change without owner-governed checkpoints; calibration continuity (CONFIG_HASH, era stamps) must be preserved; honesty over polish is the prime directive.

## Current-state inventory (layers touched or assessed)
| Layer | Before | Provenance | Fit | Research tier |
|---|---|---|---|---|
| Language / runtime | Python 3.12, stdlib only | Authored (audit batch 12, security control) | Appropriate | A (kept) |
| Architecture | single 85 KB file | Authored | Appropriate | A (kept) |
| Persistence | JSON in git, commit-back | Validated inheritance | Appropriate | A (kept) |
| Deployment | GitHub Actions cron + Pages | Authored (paper phase) | Appropriate for paper | A (kept) |
| Charts | hand-rolled inline SVG | Authored (no-CDN) | Appropriate; had a11y gap | B (fixed a11y) |
| Visual system | dark terminal palette, CSS vars | Authored | Appropriate | C (kept) |
| Risk display (By city) | uncapped rows | Accidental defect | Underbuilt | A (fixed) |
| Sizing scorer | `size_play` + dead `tier_for` | Mixed (dead residue) | Overbuilt (dead) | B (cleaned) |
| Repo hygiene | tracked .pyc, no .gitignore | Accidental | Underbuilt | C (fixed) |

## Intensive research completed
No stack or service was migrated, so no new candidate matrices were required. The consequential architectural layers (language, single-file structure, stdlib-only, JSON-in-git, GitHub Actions platform, hand-rolled SVG, no framework) were each researched and justified during the prior 12-batch audit (see `audit/AUDIT_TODO.md` section 20 and the HANDOFF Decision Log). Those recommendations were re-checked against the product truth and re-affirmed. Changing any of them "to look less generated" would violate the product's actual constraints and was explicitly declined.

## Stack and service decisions
| Layer | Before | After | Why | Migration | Rollback | Cost impact |
|---|---|---|---|---|---|---|
| (none) | n/a | n/a | No technology replaced; residue was defects and docs, not stack fit | n/a | n/a | none |

## Changes implemented
### Product and information architecture
- Exposure-cap honesty fix: cap-dropped plays no longer render as live sized bets in the By-city detail view; they show a muted "capped" tag. Persistence and the headline board were already correct.

### Visual system
- No restyle. The authored dark terminal palette, spacing, and shape language were assessed as genuinely authored (no gradient/glass/bento residue) and retained.

### Interaction states
- Added a distinct "capped" display state so the By-city view has entry, live, realized, offset, no-bet, and capped states that all match the actionable board.

### Copy
- No marketing-copy residue found. Product copy is domain-specific and truthful; retained. Fixed two factual claims in README (test count, run frequency).

### Frontend and code architecture
- Removed dead `TIER_RANK`, `tier_for`, `units_of`, the `RATING` dict, an unused `urllib.error` import, and a redundant local `random` re-import. Retained `TIER_CUTS` (documented) to preserve CONFIG_HASH.

### Backend, data, authorization, and security
- Added `.gitignore` for `__pycache__/` and `*.pyc`; untracked a committed `cpython-312.pyc`; removed a stray `audit/test` file. No auth or data-path behavior changed.

### Accessibility and performance
- The four Results charts now expose `role="img"` and a data-derived `aria-label`. Opened the optional `_style.css` override via a context manager (no file-handle leak on import).

### Testing and operations
- Added `test_capped_plays_not_actionable_in_rows`. Suite is 24/24 green.

## Files changed
| File | Purpose |
|---|---|
| `kalshi_weather.py` | caps display fix, dead-code removal, SVG accessibility, minor hygiene |
| `test_nimbus.py` | new regression test for the caps display invariant |
| `README.md` | corrected test count, run frequency, and audit-doc path |
| `HANDOFF.md` | fixed two section-10 bootstrap URLs; added v6.11 changelog entry |
| `.gitignore` | new; stop committing bytecode |
| `__pycache__/kalshi_weather.cpython-312.pyc` | removed (untracked build artifact) |
| `audit/test` | removed (stray 1-byte file) |
| `audit/RESIDUE_REMEDIATION_2026-07-21.md` | this report |

## Verification performed
| Check | Procedure | Result | Notes |
|---|---|---|---|
| Compile | `python3 -m py_compile kalshi_weather.py test_nimbus.py` | PASS | |
| Unit tests | `python3 test_nimbus.py` | PASS 24/24 | 1 added |
| Render path | offline spike: load real state, `compute_report`, `render_results` into a temp dir, HTML-parse | PASS | 233 plays scored, 76 KB well-formed HTML, 4 charts now labeled |
| Hash continuity | compare `CONFIG_HASH` to committed boards | PASS | 692c3b39 unchanged; no era split |
| Version continuity | print `MODEL_VERSION` | PASS | unchanged |
| Em-dash gate | grep U+2014 in changed files | PASS | none introduced |
| Live double-run | `CI=true python kalshi_weather.py` | BLOCKED | sandbox network policy 403s Kalshi + Open-Meteo; runs on next Actions run |

## Before-and-after audit
| Category | Before | After | Evidence |
|---|---|---|---|
| Product specificity | 9/10 | 9/10 | copy and model are domain-specific |
| Research integrity | 9/10 | 9/10 | 12-batch audit + Decision Log |
| Architecture fit | 9/10 | 9/10 | constraints justified, retained |
| Frontend / code architecture | 7/10 | 9/10 | dead code removed; caps honesty fixed |
| Accessibility | 5/10 | 8/10 | SVG charts now labeled |
| Backend / data / security | 8/10 | 8/10 | unchanged behavior; hygiene added |
| Testing | 8/10 | 9/10 | regression test added |
| Documentation accuracy | 7/10 | 9/10 | README + bootstrap URLs corrected |

## Deliberately retained common patterns
- Single-file, stdlib-only, no-framework, JSON-in-git, GitHub Actions cron, hand-rolled inline SVG, dark-only theme, Google Fonts with a system-ui fallback. Each is documented and justified by the owner's real constraints (phone-only web-UI uploads, office-network isolation, supply-chain surface, surgical verifiable edits). Replacing any to "look authored" was declined.
- `TIER_CUTS` kept (unused) to preserve CONFIG_HASH and calibration-era continuity.

## Unresolved items
| Item | Reason | Risk | Required research or action |
|---|---|---|---|
| "Brier below market" go-signal in FUTURE 6 / FUTURE 1 / LIVE_TRADING_SPEC gate 1 | Automation gate; gate/kill criteria are never changed unilaterally | Doc says an unpassable benchmark; could confuse the live go/no-go | Owner decides whether to sync it to the CLV/ROI amendment |
| `STD_OFFSET_H.get(tz,0)` UTC default | Inert for current 20 cities | A future non-listed timezone mis-windows the settlement day silently | Switch to `STD_OFFSET_H[tz]` when adding a city outside the five listed zones |
| `fget` swallows fetch errors; `resolve_pending` conflates failure with not-settled | Touches money-resolution path; wants its own test | A persistent settlement-endpoint outage leaves bets unresolved with no health signal | Distinguish transport failure from empty body; surface repeated failures to the health strip |
| README omits the 4th (shadow) cron | README is intentionally minimal | Low | Optional one-line note |
| HANDOFF 0b "root-level files" wording | Five audit docs now live under `audit/`; they are frozen history rarely handed back | Low | Optional wording update |

## Migration and rollback notes
No data migration. All code changes are behavior-preserving for pricing and persistence; the only user-visible change is that cap-trimmed plays show "capped" in By-city instead of a phantom sized bet, and the Results charts gained screen-reader labels. Rollback is a plain `git revert` of the remediation commit; there is no state or schema change, and CONFIG_HASH / MODEL_VERSION are unchanged so no calibration history is affected either way.

## Updated ADRs and project instructions
- HANDOFF changelog gained the v6.11 entry with rationale and the flagged-not-fixed list; doc version bumped to 2026-07-21 (v6.11).
- `TIER_CUTS` now carries an inline comment explaining why it is retained.
- This report is the durable record of the pass.

## What could change these decisions
- Owner approval to sync the automation-gate go-signal would move that unresolved item into a follow-up change.
- Adding a city outside the five current timezones would make the `STD_OFFSET_H` hardening worth doing in the same change.
- A measured settlement-endpoint outage would raise the priority of the `fget` / `resolve_pending` hardening.
