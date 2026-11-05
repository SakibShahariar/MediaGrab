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

## Audited range after the 2026-11-05 checkpoint

- Reviewed range: `20977452f75b5421389180954f448ad2fd7b9444..d9cf5fed12916cddf9f7ec569f024738373ed9df`
- The quality-preference durability commit passed the four-version Python matrix.
- Fedora RPM packaging had three successive failures, each inspected from job logs and fixed in the next commit. The latest Fedora build and Python matrix both passed.

| Commit SHA | Subject | Python CI | Fedora RPM CI |
|---|---|---|---|
| `9fdb7707692e20a83af705fafea9f33bcb521131` | fix(quality): sync saved preference directory | green — [42062449014](https://github.com/SakibShahariar/MediaGrab/actions/runs/42062449014) | not applicable — Fedora workflow not yet added |
| `1df3a684fa75e70078c4ebd52bf254303ba5aac0` | feat(packaging): add Fedora RPM build and metadata | green — [42063028865](https://github.com/SakibShahariar/MediaGrab/actions/runs/42063028865) | red — [42063028825](https://github.com/SakibShahariar/MediaGrab/actions/runs/42063028825) |
| `638d064052e8f09c4c920a02edcbbad31710f647` | fix(packaging): match RPM source archive filename | green — [42063354343](https://github.com/SakibShahariar/MediaGrab/actions/runs/42063354343) | red — [42063354791](https://github.com/SakibShahariar/MediaGrab/actions/runs/42063354791) |
| `f87b5996d089ba37948def57625555bf66d66544` | fix(packaging): use direct Fedora build requirements | green — [42063712837](https://github.com/SakibShahariar/MediaGrab/actions/runs/42063712837) | red — [42063712851](https://github.com/SakibShahariar/MediaGrab/actions/runs/42063712851) |
| `d9cf5fed12916cddf9f7ec569f024738373ed9df` | fix(packaging): include installed command entry points | green — [42064049913](https://github.com/SakibShahariar/MediaGrab/actions/runs/42064049913) | green — [42064050039](https://github.com/SakibShahariar/MediaGrab/actions/runs/42064050039) |

### Resolved Fedora RPM failures

1. **Source archive basename:** the spec's `Source0` expected `v0.1.0.tar.gz`, but CI generated `mediagrab-0.1.0.tar.gz`. Fixed in `638d064` by matching the generated archive name to the RPM source basename.
2. **Unrelated dynamic build requirement:** `%pyproject_buildrequires -t` pulled in `tox-current-env`, which was not a project dependency. Fixed in `f87b599` by using the normal `%pyproject_buildrequires` invocation; pytest remains an explicit build requirement.
3. **Unpackaged console scripts:** `%pyproject_save_files mediagrab` did not list the three generated `/usr/bin` entry points. Fixed in `d9cf5fe` by explicitly listing all three commands in `%files`.

Final observed result: the Fedora RPM workflow built the package successfully, validated the desktop/AppStream metadata, ran the Python tests, and listed the RPM contents. Real Fedora installation and GNOME launch validation remain outside CI.

## Previous checkpoint (superseded)

- Repository: `SakibShahariar/MediaGrab`
- Default branch: `main`
- Reviewed checkpoint: `d9cf5fed12916cddf9f7ec569f024738373ed9df`
- Reviewed: 2026-11-05
- Next session: audit commits newer than this checkpoint. Carry forward the exact-SHA unavailable note for `7d6f720`; its descendant tree passed run `42061649803`.

## Session history

| Date | Reviewed range / checkpoint | Result summary |
|---|---|---|
| 2026-11-02 | Initial checkpoint: `96dc9c81cfefec02d4bddea5693de9cccc35a677` | Baseline established. |
| 2026-11-05 | `96dc9c8..2097745` (27 commits) | 25 direct green/red runs reviewed; one regression diagnosed and fixed; one exact-SHA run unavailable but descendant tree green. |
| 2026-11-05 | `2097745..d9cf5fe` (5 commits) | Python matrix green throughout; three Fedora RPM failures were diagnosed and fixed in sequence; latest Fedora RPM build is green. |
| 2026-11-05 | `d9cf5fe..090ed3c` (5 commits) | All five commits have directly observed green Python and Fedora RPM workflows; issues #41 and #42 closed. |
