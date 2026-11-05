# Final enhancements — 2026-11-05

## 1. Correctness oracle
- Added optional trusted reference C program support through `--reference-program`.
- The reference is compiled independently and receives the same stdin, argv and staged input files as the student executable.
- Its stdout becomes the expected stdout for that case. Explicit `expected_output` remains supported.
- Reference compilation failure is fatal to the grading run rather than silently falling back to guessed expected output.
- Expected generated files still require explicit expected-file expectations; reference-program output-file inference is not claimed.

## 2. Originality review signals
- Similarity now combines normalized token-pair Dice similarity (60%) with normalized token-sequence similarity (40%).
- Reports each component, reference identity and token-pair counts.
- High similarity remains a human-review flag, not a plagiarism or LLM-authorship verdict.

## 3. Optional execution isolation
- Added optional Linux Bubblewrap execution mode, controlled by `execution.sandbox_mode`.
- When enabled, the runner requests network namespace isolation, read-only host filesystem visibility, and a writable per-test working directory.
- Missing Bubblewrap causes a fail-closed error; the program is not executed.
- Default remains `off` to preserve compatibility. Test on the target Linux host before enabling.
- This is defense-in-depth, not a complete security sandbox.

## Verification
- Python AST syntax validation: passed for all project Python files.
- Unit/integration tests: 32 passed, 1 skipped because ASan runtime was incompatible/unavailable in the test environment.
- New regression tests cover reference-oracle matching and mismatch, dual similarity evidence, and Bubblewrap fail-closed behavior.
