# AutoGrader — Rule-Driven Evaluator for C Programs

A modular C assignment grader. It compiles a submission, performs a first-pass smoke check, runs configured analyzers, combines scoreable metric results according to an external JSON rubric, and writes JSON/text feedback reports.

## Linux lab setup

Recommended on the lab Linux machine (Ubuntu/Debian-like):

```bash
sudo apt update
sudo apt install -y python3 gcc build-essential cppcheck
python3 --version
gcc --version
```

Python 3.10+ is recommended. This implementation uses the Python standard library; no pip packages are required for the built-in deterministic analyzers. Use a disposable VM/container for unknown submissions. The runner applies POSIX `RLIMIT_AS` address-space and CPU limits when supported and kills timed-out process groups, but **this is not a complete security sandbox**. Filesystem/network isolation and process-count limits should be configured by the lab/container administrator.

## Run

From the repository root:

```bash
python3 -m src.main \
  --source tests/inputs/sum.c \
  --tests tests/sample_cases.json \
  --rules rules/rules.json \
  --output-dir reports/demo \
  --reference tests/inputs/wrong_sum.c
```

Options:

- `--source`: student C file.
- `--tests`: JSON array; each case has `input` and `expected_output`, and may have `name`.
- `--rules`: editable rubric JSON.
- `--output-dir`: report directory.
- `--timeout`: default runtime limit if the rubric omits `time_limit_s`.
- Repeat `--reference path/to/reference.c` to compare against supplied reference submissions.

The grader writes `grade_report.json` and `grade_report.txt`. The report records source/rules SHA-256 hashes, first-pass status, metric evidence, counterexamples, score breakdown, tool information, and usefulness/limitations notes. Given identical source, tests, rules, toolchain, and references, the deterministic built-in metrics are intended to return the same grade. External toolchain versions can affect behavior, so versions and hashes are reported.

## Test

```bash
python3 -m unittest discover -s tests -v
```

## Assignment-independent test suites

The grader does not select a problem template and does not assume factorial, addition, or any other particular task. The Test suite tab starts empty. For each assignment, the instructor imports or enters the exact test cases and trusted expected outputs from the assignment specification or a verified reference implementation.

A test case can provide `input` (stdin), `args` (command-line arguments), `files` (input files staged in a fresh working directory), `expected_output` (required stdout oracle), and optional `expected_files` (expected generated-file contents). A case must include `expected_output` and at least one of `input`, `args`, or `files`.

The system can compile and execute many kinds of C programs, including multi-file C projects and conventional Flex/Bison compiler projects, subject to the configured build mode. It cannot infer arbitrary program input grammar or intended output from C source alone. Without trusted expected outputs, correctness scoring is unavailable rather than guessed. Sanitizer/fuzz diagnostics are not substitutes for a correctness oracle.

## Rubric and analyzers

`rules/rules.json` is the example rule set. Each metric has an editable `weight` and a minimum score `threshold`; enabled weights must sum to 1.0. Analyzer-specific thresholds and parameters are kept under `params`. The example follows the assignment's nine metric categories:

1. correctness (`io_tests`)
2. syntax (`compiler_warnings`)
3. structure (`static_analysis`)
4. modularity (`function_split`)
5. logical (`edge_case_runner`, optional instructor-authored cases only; disabled by default because generated correctness edge cases are already scored under correctness)
6. complexity (`complexity_estimator`)
7. memory safety (`sanitizer_run`, GCC ASan/UBSan)
8. readability (`readability_review`, deterministic local heuristic)
9. originality (`similarity_flag`, source token-pair comparison)

The readability implementation is deliberately deterministic and offline; it is not an LLM verdict. Originality checks only the references/corpus supplied to the grader. It cannot reliably identify arbitrary online sources or prove that an LLM wrote code. Similarity flags require human review.

## Design / known limitations

- A finite test suite cannot prove correctness; the report includes failing inputs, expected output, actual output, and runtime evidence for tested cases.
- ASan/UBSan only report issues triggered in instrumented executions; a clean run is not proof of memory safety.
- Complexity, structure, modularity, and readability are source-level heuristics, not full formal C analysis.
- Process limits are best-effort controls, not a hardened sandbox. Restrict network, filesystem, processes, and capabilities outside this program for real untrusted submissions.
- Similarity comparison can produce false positives for short mandated solutions and false negatives for renamed/refactored copying.

See `docs/USEFULNESS_AND_LIMITATIONS.md` for concrete deployment examples.


## Batch grading and sample outputs

The Streamlit interface supports multiple `.c` uploads and applies the same test suite and rubric
to each submission independently. It exports a CSV summary and a ZIP containing individual JSON
and text reports. When enabled, each uploaded submission is compared with the others as a
similarity-review signal; this is not a plagiarism verdict.

Generate the five reproducible sample reports (correct, wrong answer, compile failure, infinite
loop, and memory error) with:

```bash
python3 scripts/generate_sample_reports.py
```

The resulting files are stored under `reports/sample_outputs/`. The report-generation log records
the command and process exit status for each example. Sanitizer availability is environment
dependent; reports must retain an explicit unavailable status rather than treating it as a clean
memory-safety result.

## Execution-failure grading policy

The default rubric includes `grading_policy.first_pass_failure`. If compilation succeeds but the
first-pass smoke execution times out, crashes, or returns an execution error, execution-based
correctness analyzers are not run. The report marks correctness as `not_run`, sets grade status to
`execution_blocked`, emits a review flag, and caps the weighted diagnostic score at 20/100. The cap
is configurable in `rules/rules.json`. This prevents a non-terminating submission from receiving
a high apparent grade based only on static source metrics. Compile failures use the separate
`compile_failure_score` policy.

See [SECURITY_SANDBOX.md](docs/SECURITY_SANDBOX.md) before evaluating untrusted code.

## Flex/Bison compiler-project submissions

The Streamlit UI also has a **Flex/Bison compiler project (.zip)** submission mode for conventional single-lexer/single-parser C projects. Upload a ZIP containing exactly one `.l` file, one `.y`/`.yy` file, and supporting `.c`/`.h` files. A GitHub-style ZIP with one enclosing top-level folder is accepted. The builder runs Bison, then Flex, then GCC; it does **not** execute a student-supplied Makefile or arbitrary shell script.

Install the required Linux toolchain in WSL:

```bash
sudo apt update
sudo apt install -y flex bison gcc
```

For the Ciitp-to-C compiler assignment, import an instructor/reference JSON test suite in the Test suite tab. Each case must contain `input` (a valid or invalid Ciitp program supplied on stdin) and `expected_output` (the compiler's expected stdout). Example shape:

```json
[
  {
    "name": "simple_block",
    "input": "<Ciitp source text here>\\n",
    "expected_output": "<trusted expected compiler output here>\\n"
  }
]
```

Use trusted outputs from the assignment specification or a verified reference compiler. Include valid programs, malformed syntax, nested blocks, decisions, process definitions, and control-flow cases where those are part of the language contract. If the compiler writes generated C/graph output to files instead of stdout, this current test adapter needs an assignment-specific output-capture rule; do not pretend stdout comparison verifies file output.

For project submissions, source-quality metrics inspect the selected primary C file (`main.c`, then `driver.c`, otherwise the first `.c`). ASan/UBSan rebuilding is skipped for the multi-file project mode in this release; ordinary bounded execution tests still run. The build pipeline assumes one `.l`, one `.y`/`.yy`, GCC-compatible C, and generated parser header `myyacc.tab.h` conventions. Projects with multiple lexers/parsers, custom build systems, C++, or nonstandard generated-file conventions need a project-specific build adapter.


## Universal assignment configuration (updated)

The grader is assignment-agnostic at the execution/build layer. It accepts:

- A standalone `.c` file compiled with GCC.
- A ZIP containing a multi-file C project in nested folders.
- `auto` project build detection: conventional Flex/Bison pair when one `.l` and one `.y`/`.yy` exist; otherwise compile all `.c` files recursively.
- Explicit `gcc`, `flex_bison`, or `custom` build modes. Custom build steps are JSON argv arrays; no shell, Makefile, or uploaded script is executed. Only `gcc`, `clang`, `flex`, and `bison` are allow-listed.
- Per-case stdin, command-line arguments, staged input files, stdout expectations, and expected generated-file contents.

Example test case:

```json
[
  {
    "name": "cli_and_file_case",
    "input": "",
    "args": ["--input", "input.txt"],
    "files": {"input.txt": "sample data\n"},
    "expected_output": "completed",
    "expected_files": {"result.txt": "expected result\n"}
  }
]
```

For a new assignment, the instructor must provide trusted expected outputs or an independent reference oracle. The system does not infer arbitrary program semantics from C source. The instructor UI contains no built-in problem templates; the test suite starts empty and requires assignment-specific trusted cases.

Project ZIP safety limits: at most 500 entries and 50 MB uncompressed; path traversal is rejected. Build commands are executed without a shell. Runtime resource limits are still not a complete security sandbox; use a disposable restricted container/VM for untrusted student code.


## Final verification notes (2026-11-05)

The final packaging validation completed Python compilation and **32 automated unit/integration tests successfully (one sanitizer test skipped because the ASan runtime was unavailable/incompatible)**. Coverage includes bounded execution, timeout/score-cap behavior, memory-safety detection where the host sanitizer runtime is available, project ZIP build checks, argv/file-based test cases, and similarity normalization.

The first-pass smoke check uses the first trusted test case's stdin, command-line arguments and staged input files. Output-limit termination is treated as an execution-blocking failure for score-cap purposes. The interactive Streamlit browser was not launched in the packaging environment; complete the manual UI checklist below in the target WSL/Linux environment before submission.

### Final local UI checklist
1. Run `streamlit run app.py` and confirm the page loads without a traceback.
2. Confirm the Test suite tab starts empty and has no built-in factorial/addition template.
3. Import a trusted JSON test suite for the actual assignment and verify readiness.
4. Grade one correct, one wrong-answer, one compile-error and one infinite-loop sample.
5. Confirm wrong-answer evidence shows input, expected output and actual output; confirm the infinite-loop report is execution-blocked and capped.
6. Export and open both JSON and text reports.
7. For a Flex/Bison project demo, install `flex` and `bison` and verify the ZIP layout before recording.

### Scope and honest claims
The implementation is reusable across C assignment types at the build/execution layer, but it is not an oracle for arbitrary C semantics. Correctness and counterexample feedback depend on assignment-specific trusted test cases or a verified reference program/oracle. Complexity, structure, modularity and readability checks are heuristics. Similarity flags compare only against supplied references/corpus; they cannot prove online copying or LLM authorship. ASan/UBSan only detect defects reached by executed test paths. The process runner is not a hardened sandbox.


## Final enhancement: reference oracle, stronger similarity, optional Linux isolation

### Reference-program correctness oracle
The CLI accepts `--reference-program path/to/trusted_reference.c`. The reference is compiled separately and run with the same stdin, command-line arguments and staged input files as the student program. Its stdout becomes the expected output for each case. In this mode, test cases may omit `expected_output`; they must still provide the inputs needed to exercise the program. The reference must be trusted, deterministic, safe to execute, and compatible with the same input contract. `expected_files` comparisons continue to use explicitly configured expected file contents; this release does not infer expected generated files from a reference program.

Example:
```bash
python3 -m src.main --source submissions/student.c --tests tests/oracle_inputs.json \
  --reference-program instructor/reference.c --rules rules/rules.json --output-dir reports/reference
```
Each test case can be as small as:
```json
[{"name":"sample","input":"input data\n","args":[]}]
```
Do not use the student's own output as the expected answer. The reference program is an oracle only if the instructor has independently validated it.

### Stronger originality similarity signals
The similarity analyzer now combines normalized token-pair Dice similarity (60%) and normalized token-sequence similarity (40%). It reports both component scores, best reference, and token-pair evidence. Similarity remains a corpus-bounded human-review signal; it cannot establish authorship, detect all online/LLM sources, or prove misconduct.

### Optional Bubblewrap isolation
Install Bubblewrap on supported Linux hosts (`sudo apt install bubblewrap`). Set `execution.sandbox_mode` to `bubblewrap` in `rules/rules.json` to request a separate network namespace and a read-only host filesystem with only the per-test working directory writable. If Bubblewrap is unavailable, the runner fails closed and does not execute the submission. Default is `off` for compatibility. This is defense-in-depth, not a substitute for a disposable VM/container, seccomp/AppArmor policy, cgroups and administrator-controlled isolation. Review local Bubblewrap policy and test it on the target host before enabling it for real submissions.


See [FINAL_ENHANCEMENTS.md](FINAL_ENHANCEMENTS.md) for the three final upgrades and verification details.
