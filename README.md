# AutoGrader – C Programming Assignment Evaluator

AutoGrader is a web-based tool for grading C programming assignments. It compiles and runs student programs, checks them using instructor-provided test cases, analyses selected code-quality measures, calculates scores using a configurable rubric, and generates reports.

It supports:
- Single C source files (`.c`)
- Supported multi-file C projects (`.zip`)
- Conventional Flex/Bison compiler projects
- Individual grading and batch grading of multiple C files

---

## 1. Requirements

Use **Ubuntu Linux** for the simplest setup. On Windows, install **WSL2 with Ubuntu** and follow the same instructions inside the Ubuntu terminal.

Required:
- Python 3
- GCC and build tools
- Git

Optional:
- Flex and Bison – only needed for Flex/Bison compiler projects
- Bubblewrap – only needed if you want to use the optional Linux isolation mode

---

## 2. Install AutoGrader on a new laptop or lab computer

Follow these steps on **every computer** where you want to run AutoGrader.

### Step 1 – Open a terminal

On Ubuntu, open Terminal.

On Windows, open the Ubuntu application installed through WSL2. Do not run the Linux commands below in Windows Command Prompt or PowerShell.

### Step 2 – Install the required system tools

Copy and run:

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip build-essential gcc
```

If you will test Flex/Bison projects or Bubblewrap isolation, also run:

```bash
sudo apt install -y flex bison bubblewrap
```

Check the installations:

```bash
python3 --version
gcc --version
git --version
```

### Step 3 – Download the project from GitHub

Run:

```bash
git clone https://github.com/vikas0127/AutoGrader-C-Program-Grading.git
```

Move into the downloaded project folder:

```bash
cd AutoGrader-C-Program-Grading
```

### Step 4 – Create a Python virtual environment

Run:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

After activation, `(.venv)` should appear at the beginning of your terminal prompt.

**Important:** Create a separate virtual environment on each laptop. Do not copy the `.venv` folder from another computer.

### Step 5 – Install the Python packages

Run:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements-ui.txt
```

Wait for the installation to finish.

### Step 6 – Run the automated tests

Run:

```bash
python -m unittest discover -s tests -v
```

The tests should finish with an `OK` result. If a test is skipped because a tool such as the sanitizer runtime is unavailable, read the test output to see which optional tool is missing.

### Step 7 – Start AutoGrader

Run:

```bash
streamlit run app.py
```

Open the local address shown in the terminal. It is normally:

```text
http://localhost:8501
```

Keep the terminal open while using the application. To stop AutoGrader, press `Ctrl + C` in that terminal.

---

## 3. How to use the application

### Step 1 – Configure the rubric

Use the **Instructor Console** on the left side of the application.

- Keep the default rubric or import an instructor-provided rubric JSON file.
- Enable or disable the required metrics.
- Check that the enabled metric weights are normalized as required by the application.

### Step 2 – Add the assignment test cases

Open the **Test suite** tab.

- Import the instructor's test-suite JSON file, or enter the test cases.
- The test suite starts empty. This is intentional: AutoGrader does not assume that every assignment is an addition, factorial, or any other fixed problem.
- Use trusted expected outputs from the assignment specification or a verified reference implementation.

A test case can contain:
- `input` – text sent to standard input
- `args` – command-line arguments
- `files` – input files created in the test working directory
- `expected_output` – expected standard output
- `expected_files` – expected contents of files created by the program

Correctness grading needs trusted expected outputs or a trusted reference program. AutoGrader cannot guess the intended output of an arbitrary C program.

### Step 3 – Upload a student submission

Open the **Submission** tab.

- For one C file, choose **Standalone C program** and upload the `.c` file.
- For a supported multi-file C project, choose the ZIP project option and upload the project `.zip`.
- For a Flex/Bison compiler project, choose the Flex/Bison project option and upload the ZIP containing the required `.l`, `.y`/`.yy`, and supporting source/header files.

### Step 4 – Run grading

Click **Run grading pipeline**.

Review the correctness results, compiler/runtime messages, metric scores, and generated feedback.

### Step 5 – Batch grading (multiple students)

In the **Batch grading** section:

1. Upload multiple student `.c` files.
2. Keep the same assignment test suite and rubric configured.
3. Choose whether to enable pairwise similarity review.
4. Click **Grade all submissions**.
5. Review the individual results and download the batch summary/reports offered by the application.

Batch grading applies the same configured assignment tests and rubric to each uploaded submission. It does not automatically create a different test suite for each student.

---

## 4. Flex/Bison projects

Flex and Bison are optional system tools. Install them if you need to grade a compiler assignment:

```bash
sudo apt install -y flex bison
```

For the supported Flex/Bison project mode, upload a ZIP containing:
- One `.l` lexer file
- One `.y` or `.yy` parser file
- Required supporting `.c` and `.h` files

The project builder runs Bison, Flex, and GCC. It does not run an uploaded Makefile or arbitrary shell script. The current adapter expects a conventional single-lexer/single-parser project and the generated parser-header convention documented in the project.

---

## 5. Optional Bubblewrap isolation

Bubblewrap is an optional Linux restriction layer for running submissions. It is not required to launch the application.

Install and check it:

```bash
sudo apt install -y bubblewrap
which bwrap
bwrap --version
```

To request Bubblewrap mode, set `execution.sandbox_mode` to `bubblewrap` in `rules/rules.json`. The default is `off`.

Bubblewrap availability and policies differ between Linux distributions and WSL environments. Test it on the target computer before enabling it. Resource limits and Bubblewrap are **not a complete security sandbox**. For untrusted submissions, use an institution-managed disposable VM or restricted container with administrator-controlled security settings.

---

## 6. Command-line grading (optional)

The command-line interface can grade a standalone C file using a test suite and rubric:

```bash
python3 -m src.main \
  --source tests/inputs/sum.c \
  --tests tests/sample_cases.json \
  --rules rules/rules.json \
  --output-dir reports/demo
```

To use an instructor-validated reference C program as the expected-output oracle:

```bash
python3 -m src.main \
  --source submissions/student.c \
  --tests tests/oracle_inputs.json \
  --reference-program instructor/reference.c \
  --rules rules/rules.json \
  --output-dir reports/reference
```

The reference program must be trusted, deterministic, and independently checked by the instructor. Expected generated-file contents still need to be provided explicitly in `expected_files`.

The command-line grader writes `grade_report.json` and `grade_report.txt` in the selected output directory.

---

## 7. Troubleshooting

**`streamlit: command not found`**

Make sure the virtual environment is activated, then run:

```bash
python -m pip install -r requirements-ui.txt
```

**`pip: command not found`**

Install the Python virtual-environment and pip packages:

```bash
sudo apt install -y python3-venv python3-pip
```

Then repeat Step 4 and Step 5.

**`gcc: command not found`**

Run:

```bash
sudo apt install -y build-essential gcc
```

**The application does not open in the browser**

Check the terminal for an error. Make sure Streamlit is still running and open the exact local URL printed in the terminal, normally `http://localhost:8501`.

**Bubblewrap does not work**

Check `bwrap --version`. Some WSL or managed lab environments restrict the namespaces Bubblewrap needs. Leave sandbox mode as `off` unless Bubblewrap has been successfully tested on that machine.

---

## 8. Important limitations

- Correctness results depend on the quality and coverage of the instructor's test cases or trusted reference program. Passing a finite test suite does not prove that a program is fully correct.
- Complexity, structure, modularity, and readability checks are heuristics, not formal proofs.
- AddressSanitizer and UndefinedBehaviorSanitizer detect only problems reached during the executed tests.
- Similarity checks compare submissions only with the supplied reference corpus. A similarity flag is for human review; it does not prove plagiarism or AI authorship.
- Execution time/memory limits and Bubblewrap are not a complete security boundary. Use a restricted VM/container for untrusted code.

---

## 9. Project links

- GitHub repository: https://github.com/vikas0127/AutoGrader-C-Program-Grading
- Security notes: [docs/SECURITY_SANDBOX.md](docs/SECURITY_SANDBOX.md)
- Final enhancements: [FINAL_ENHANCEMENTS.md](FINAL_ENHANCEMENTS.md)
- Usefulness and limitations: [docs/USEFULNESS_AND_LIMITATIONS.md](docs/USEFULNESS_AND_LIMITATIONS.md)

