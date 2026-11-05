# Usefulness and Limitations

## Usefulness in real-life settings (concrete examples)

1. **Large programming courses:** an instructor evaluates 300 submissions against the same hidden tests and rubric; the agent gives consistent first-pass grades and a per-test record, reducing repetitive manual execution.
2. **Student debugging feedback:** a sum program fails on `2147483647 1`; the report shows the input, expected output, actual output or sanitizer diagnostic, allowing the student to reproduce the issue.
3. **Code-quality screening:** an introductory programming course uses compiler warnings, structure, modularity, and readability indicators alongside correctness, so evaluation reflects more than output alone.
4. **Originality triage:** a course corpus comparison flags a pair above a configured 0.85 similarity threshold; the instructor reviews the evidence rather than treating the metric as an automatic plagiarism verdict.

## Concrete limitations (each with a potentially unreliable verdict)

1. **Finite tests cannot establish correctness.** Example: a program passes all provided tests but fails on an untested integer boundary or unusual whitespace; the grader still reports the tested cases as passing. Mitigation: add domain-specific hidden and generated tests, and use a trusted oracle where possible.
2. **Dynamic sanitizers have path coverage limits.** Example: a use-after-free exists only in a branch not reached by any test; ASan reports no issue, producing a false sense of safety. Mitigation: expand test coverage and use fuzzing where practical.
3. **Similarity can mislead.** Example: two students independently implement a very short required loop and exceed the threshold (false positive), or copied code is renamed/refactored enough to fall below it (false negative). Mitigation: human review and multiple evidence sources; similarity alone is not proof of copying or LLM use.
4. **Static heuristics can misestimate program properties.** Example: a loop has a data-dependent bound or a macro obscures control flow; a lexical complexity estimator classifies it incorrectly. Mitigation: report the heuristic and evidence, not a formal guarantee; supplement with specialist tools.

## Security boundary

The grader has wall-clock timeouts and POSIX resource-limit support, but it is not a hardened sandbox. A malicious C program may still attempt filesystem/network access or exploit the host. Run submissions inside a restricted, disposable Linux container/VM with externally enforced memory, CPU, process, filesystem, and network restrictions.

## Assignment-independent operation and correctness oracle

The grader has no hard-coded problem template in its UI. It accepts instructor-authored test suites for the assignment at hand. Each test case supplies stdin, command-line arguments, and/or staged input files together with trusted expected stdout and optional expected generated-file contents. This makes the execution/build pipeline reusable across different C assignments, including compiler projects, while keeping the correctness oracle specific to the assignment contract.

The grader does not claim to infer arbitrary C semantics from source code. If no trusted expected outputs or independent reference oracle are available, correctness cannot be established; the instructor must provide an oracle or treat runtime/sanitizer results as diagnostics only.

### Validation performed for this release

- UI no longer exposes factorial or add-two-integers templates.
- New sessions begin with an empty test suite; no unrelated cases are silently applied.
- Existing test-suite validation requires expected output and a supported input channel.

### Remaining deployment caveat

The runner applies process time, memory, output and process-group limits where supported, but these controls are not a complete hostile-code sandbox. Run untrusted submissions in a disposable, network-isolated container or VM with restricted filesystem and user privileges.


## Improvements in the final enhanced release

- Correctness can now use either explicit expected outputs or a separately compiled trusted C reference program (`--reference-program`) for stdout comparison on identical inputs/arguments/staged files. The oracle must be validated by the instructor. Expected generated files still require explicit expected-file expectations.
- Originality comparison combines normalized token-pair and sequence similarity, and reports component scores and reference evidence. It remains a review lead, not a plagiarism/LLM detector.
- Linux deployments can optionally request Bubblewrap isolation using `execution.sandbox_mode: bubblewrap`. The runner fails closed if Bubblewrap is requested but unavailable. This is additional isolation, not a complete security guarantee.
