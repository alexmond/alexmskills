# Tap one-liners, by tool

`progress_tap.py` sits in a pipe, forwards every byte unchanged, and reads the
position the tool already prints. Nothing in your build changes except the
pipe.

```bash
TAP="python3 <plugin>/scripts/progress_tap.py"
```

Three rules apply to every line below:

- **Merge stderr** with `2>&1`. Most tools print progress there.
- **The pipeline's exit code is the tap's.** Read `${PIPESTATUS[0]}` for the
  tool's own verdict, or set `set -o pipefail`.
- **Some tools go quiet in a pipe.** The flag that turns their position output
  back on is in the table.

## Measured — the tool prints done and total

| Tool | Command | Needs |
|---|---|---|
| Maven | `mvn -B verify 2>&1 \| $TAP 'build'` | a multi-module reactor (a single module prints no `[n/m]`) |
| git | `git clone --progress <url> 2>&1 \| $TAP 'clone' --pattern git` | `--progress` |
| Docker / Podman | `docker build --progress=plain -t app . 2>&1 \| $TAP 'image' --pattern docker` | `--progress=plain` |
| Ninja, Meson, Bazel | `ninja -C build 2>&1 \| $TAP 'compile' --pattern ninja` | — |
| anything printing `N/M` | `./migrate.sh 2>&1 \| $TAP 'migrate' --pattern ratio` | — |

## Percent — the tool prints its own percentage

| Tool | Command | Needs |
|---|---|---|
| pytest | `pytest 2>&1 \| $TAP 'tests' --pattern pytest` | the default (non `-q -q`) output |
| CMake (Makefiles) | `cmake --build build 2>&1 \| $TAP 'compile' --pattern cmake` | — |
| rsync | `rsync -a --info=progress2 src/ dst/ 2>&1 \| $TAP 'sync' --pattern rsync` | `--info=progress2` |
| anything printing `NN%` | `./export.sh 2>&1 \| $TAP 'export' --pattern percent` | — |

## Counted — one line per finished unit

These have no denominator on the line. The bar shows a count, and from the
second run an estimate learned from the first. Pass `--total` when you can
compute it, and the bar is exact from the first run.

| Tool | Command | A total, if you want one |
|---|---|---|
| Gradle | `./gradlew build --console=plain 2>&1 \| $TAP 'build' --pattern gradle` | `--total "$(./gradlew build --dry-run --console=plain \| grep -c '^:')"` |
| Cargo | `cargo build 2>&1 \| $TAP 'build' --pattern cargo` | `--total "$(cargo tree --prefix none \| sort -u \| wc -l)"` (approximate) |
| Go | `go test ./... 2>&1 \| $TAP 'tests' --pattern go` | `--total "$(go list ./... \| wc -l)"` |
| Jest / Vitest | `npx jest 2>&1 \| $TAP 'tests' --pattern jest` | `--total "$(npx jest --listTests \| wc -l)"` |
| .NET | `dotnet build 2>&1 \| $TAP 'build' --pattern dotnet` | `--total "$(dotnet sln list \| grep -c proj)"` |
| Terraform | `terraform apply -auto-approve 2>&1 \| $TAP 'apply' --pattern terraform` | the `Plan: N to add…` figure |
| Ansible | `ansible-playbook site.yml 2>&1 \| $TAP 'deploy' --pattern ansible` | `--total "$(ansible-playbook site.yml --list-tasks \| grep -c TAGS)"` |
| Spring Batch | `java -jar job.jar 2>&1 \| $TAP 'batch' --pattern batch` | the number of steps |
| your own tool | `./tool 2>&1 \| $TAP 'work' --pattern 'count:^done: ' --total 800` | you know it |

## When there is no pattern

A tool that prints nothing useful (`npm install`, `ffmpeg`, `tar`) cannot be
tapped. Wrap it instead — the job is timed, and from the second run the
channel shows time left learned from the first:

```bash
python3 <plugin>/scripts/progress.py run --name 'npm install' -- npm install
```

If the tool has a status command you can poll, mirror that instead (see
`mirror` in SKILL.md).

## Inside a pipeline

Export `PROGRESS_PARENT` once and every tap below nests under it, the same as
any other job:

```bash
T=$(python3 <plugin>/scripts/progress.py start --name 'release' --total 3)
export PROGRESS_PARENT=$T
cargo build --release 2>&1 | $TAP 'compile' --pattern cargo
cargo test 2>&1            | $TAP 'test'    --pattern cargo
docker build --progress=plain . 2>&1 | $TAP 'image' --pattern docker
python3 <plugin>/scripts/progress.py finish "$T"
```
