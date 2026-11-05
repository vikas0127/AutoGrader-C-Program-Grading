# Universal AutoGrader update

This release is not tied to factorial, addition, or the compiler assignment. It accepts standalone C submissions and multi-file C project ZIPs.

## Supported submission/build modes

- Standalone `.c`: compiled with GCC by the existing bounded runner.
- Multi-file ZIP / `auto`: if the archive contains a conventional single `.l` plus one `.y`/`.yy`, run Flex/Bison generation and compile all C sources; otherwise compile all `.c` sources recursively with GCC.
- Multi-file ZIP / `gcc`: compile all C sources recursively. Header include directories are added automatically.
- Multi-file ZIP / `flex_bison`: explicitly use the Flex/Bison toolchain.
- Multi-file ZIP / `custom`: instructor supplies an ordered JSON list of argv arrays. Only `gcc`, `clang`, `flex`, and `bison` are allowed; there is no shell and no Makefile/script execution. Placeholders are `{project}`, `{build}`, and `{exe}`.

ZIP extraction rejects path traversal and enforces a maximum of 500 entries and 50 MB uncompressed size.

## Test contract

Each case requires `expected_output` and at least one of `input`, `args`, or `files`. Optional fields:

- `input`: text sent to stdin.
- `args`: command-line argument array.
- `files`: mapping of relative input filenames to text content staged in a fresh per-test working directory.
- `expected_files`: mapping of relative generated filenames to expected text content.

Example:

```json
[
  {
    "name": "file-and-argument-case",
    "input": "",
    "args": ["--input", "input.txt"],
    "files": {"input.txt": "hello\\n"},
    "expected_output": "completed",
    "expected_files": {"result.txt": "HELLO\\n"}
  }
]
```

The grader deliberately starts with an empty test suite. There are no factorial/addition problem templates in the instructor UI. For any assignment, the instructor must provide a trusted expected-output suite or independent oracle. A generic system cannot infer arbitrary program semantics from C source.

## Project-wide analysis

Syntax, structure, modularity, complexity, and readability analyzers run across all submitted `.c` files and report mean scores plus per-file evidence. Similarity/originality comparison uses the combined C source corpus. Memory sanitizer instrumentation supports ordinary multi-file C projects; generated Flex/Bison projects are explicitly marked skipped for this metric until generated-code sanitizer support is validated.

## Security boundary

Build steps are executed without a shell and with an allow-list of tools. Runtime process time/output/address-space limits are not a complete sandbox. Use an isolated disposable container or VM with filesystem/network restrictions for untrusted student submissions.

## Validation performed for this release

- Python syntax compilation: passed.
- Unit/integration tests: 31 passed.
- Sample reports regenerated for correct, wrong-answer, compile-failure, infinite-loop, and memory-error submissions.
- Streamlit browser startup was not verified in the build environment because Streamlit is not installed there. Install `requirements-ui.txt` in the project's virtual environment before launching the UI.
