# Commit CI Audit Ledger

Persistent repository-specific record of commit-level CI checks and red-cross investigations.

## How to use this ledger

1. Read this file before auditing commit checks.
2. Check only commits newer than the checkpoint, plus older **red**, **pending**, or explicitly unresolved entries.
3. Record exact commit SHAs and observed results; never infer from missing badges or empty API responses.
4. Preserve failures and append diagnosis, fix, rerun, and final-outcome evidence.
5. Advance the checkpoint only after reviewing the range; carry unresolved entries forward.

## Result meanings

| Result | Meaning |
|---|---|
| **green** | Completed successful check/run directly observed. |
| **red** | Completed failing check/run directly observed. |
| **pending** | Check/run exists but is unfinished. |
| **unavailable** | Available evidence did not expose a result; not a pass or failure. |
| **not applicable** | Workflow configuration confirms no relevant check is triggered. |

## Audited range: 2026-11-02 through 2026-11-05

- Reviewed range: `96dc9c81cfefec02d4bddea5693de9cccc35a677..20977452f75b5421389180954f448ad2fd7b9444`
- 25 commits have directly observed green/red runs. Commit `7d6f720` has no run attached to its exact SHA, but its code is included in the descendant tree tested successfully by run `42061649803`.
- Every observed run was checked for completion; the MP4/MKV failure was inspected at the job-log level.

| Commit SHA | Subject | Result | Run |
|---|---|---|---|
| `dfe7c9e462eeb61f077f0f1199bde5469876c563` | docs: add persistent commit CI audit ledger | green | 41456790218 |
| `0642281023b571e92347c3a3cc907e2d4fbe605d` | docs: document incremental commit CI auditing | green | 41456797359 |
| `dea51ae7d2eaf7a1d016202d0c34bde9937ef5ae` | docs: define issue triage categories | green | 41573516195 |
| `f5693bb7c464e35b4330fbcf4787b0a44d8ff73b` | docs(agents): define administrative commit hygiene | green | 41598092094 |
| `d875170efd53209caafcf57e9aaba24a1c403286` | chore(license): add GPL-3.0-or-later license | green | 41635271664 |
| `9b9abd93946696696c54d85a932928c5e15cee5d` | fix(browser): allow capture in browser-permitted private windows | green | 41636562697 |
| `a27ae5cc5078a76b097d9b02f17de4e8e03dc6f3` | fix(license): use canonical GPLv3 license text | green | 41637016343 |
| `3890cf2bebe37dee9d36dc45d19ff5827dfa9cbc` | feat(duplicates): detect matching completed files | green | 41637767984 |
| `40a1d78e224210905be629fb7c85aa433dcae36d` | feat(duplicates): prompt before repeat completed downloads | green | 41638555861 |
| `5bb0847b5fac354e2c12b860fc6b081d82283fbc` | feat(duplicates): support safe replace and remembered choices | green | 41640666329 |
| `8758360003c88e9c9539f0cdeb69bc1f195e3dce` | feat(duplicates): allow clearing remembered choice | green | 41640806068 |
| `e40a686680bd25ec4ab521bce6095657a47c1d74` | feat(duplicates): compare supplied checksums | green | 41641028521 |
| `cbc21547e0a639dba11d42b7ba7cfab3f8f6de92` | feat(duplicates): detect completed URL repeats | green | 41641221730 |
| `f5bd37d7d0eeb477db81cd0f8ef5e72570849c0c` | fix(duplicates): restrict replace to matching saved files | green | 41641397335 |
| `efad6886cd12cb7e636ccd146b10493459d3feac` | docs(agents): clarify acceptance criteria evidence | green | 41864198035 |
| `2fd1807fcb5d83b44a8f189c9a50ee8fcfb9be88` | feat(streams): allow MP4 or MKV output for manifests | red | 42035920218 |
| `94ef8a8fb76c16e10a1320e3159f65b73d8cec76` | fix(queue): persist selected stream container | green | 42036058632 |
| `f25855fb93d517e5f7cdad78cb92fcc509b743ea` | test(streams): cover MP4 muxing compatibility errors | green | 42036248279 |
| `c608aed99668c3b53f9459715e2c5a458634e741` | fix(dash): avoid treating segmented resources as direct files | green | 42056677498 |
| `384a05d12d1ee9a4109cfe98c6bb8291f807c4b7` | feat(dash): expose dynamic MPD availability metadata | green | 42060044532 |
| `1d0f62fc0a6f7166146fd36c2c33e66457e0f3cc` | docs(dash): clarify live manifest limitations | green | 42060204894 |
| `003d1600601bb948bd450a36f73e610fd8ba09c7` | test(dash): cover inherited segment addressing scopes | green | 42060360122 |
| `70b9879a22388d68e580cbe74ac0c6924042ac4e` | feat(cli): add built-in command help | green | 42060540000 |
| `42f514e8e7d41462b08f769446f78d5acf2cbe2d` | docs(cli): include help command in usage examples | green | 42060657037 |
| `ed7e90df5709a064d5f9c0f1740e86f74f6c8f64` | test(cli): verify help covers every command | green | 42060747886 |
| `7d6f720917ecf99e2a4a5e699f25d1e7e62204cd` | feat(quality): remember preferred video resolution | unavailable | — |
| `20977452f75b5421389180954f448ad2fd7b9444` | docs(quality): describe remembered resolution preference | green | 42061649803 |

### Resolved red-cross: MP4/MKV output selection

- Failed commit: `2fd1807fcb5d83b44a8f189c9a50ee8fcfb9be88`; run [42035920218](https://github.com/SakibShahariar/MediaGrab/actions/runs/42035920218).
- All four Python jobs failed in `Run tests` at `test_output_format_survives_queue_persistence_and_invalid_values_are_dropped`: queue serialization omitted the selected `output_format`.
- Classification: regression introduced by the feature commit.
- Fix: `94ef8a8fb76c16e10a1320e3159f65b73d8cec76` persists the selected format. Run [42036058632](https://github.com/SakibShahariar/MediaGrab/actions/runs/42036058632) passed all four Python versions; regression coverage in [42036248279](https://github.com/SakibShahariar/MediaGrab/actions/runs/42036248279) also passed all four.
- Final outcome: resolved in the subsequent main tree; issue #48 remains open for live desktop validation only.

### Carried-forward unavailable result

- Commit `7d6f720917ecf99e2a4a5e699f25d1e7e62204cd` (`feat(quality): remember preferred video resolution`) has no direct workflow run for that exact SHA.
- Descendant run [42061649803](https://github.com/SakibShahariar/MediaGrab/actions/runs/42061649803) passed Python 3.11–3.14 on `2097745`, whose tree includes this implementation.
- Keep the exact-SHA result as unavailable; the resulting tree is green.

## Checkpoint

- Repository: `SakibShahariar/MediaGrab`
- Default branch: `main`
- Reviewed checkpoint: `20977452f75b5421389180954f448ad2fd7b9444`
- Reviewed: 2026-11-05
- Next session: audit commits newer than this checkpoint and carry forward the direct-CI-unavailable note for `7d6f720`.

## Session history

| Date | Reviewed range / checkpoint | Result summary |
|---|---|---|
| 2026-11-02 | Initial checkpoint: `96dc9c81cfefec02d4bddea5693de9cccc35a677` | Baseline established. |
| 2026-11-05 | `96dc9c8..2097745` (27 commits) | 25 direct green/red runs reviewed; one regression diagnosed and fixed; one exact-SHA run unavailable but descendant tree green. |
