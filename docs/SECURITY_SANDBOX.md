# Execution security and isolation

## What the built-in runner guarantees

The runner compiles C source in a temporary directory and applies bounded execution time,
stdout/stderr capture, POSIX address-space and CPU limits where supported, and process-group
termination on timeout. ASan/UBSan are used as diagnostic tools when available.

These controls are **defense-in-depth, not a complete sandbox**. They do not independently
guarantee filesystem isolation, network isolation, syscall filtering, process-count limits,
or protection from kernel/compiler vulnerabilities. A clean sanitizer run is not proof of safety.

## Recommended deployment for untrusted student code

Run the entire AutoGrader application inside a disposable, patched Linux VM or a dedicated
container managed by the lab administrator. The isolation boundary must cover the compiler
and every student executable. Do not mount the Docker socket, host home directory, SSH keys,
cloud credentials, or other secrets into the grading environment.

Recommended controls for the isolated environment:

- non-root user; drop Linux capabilities; `no-new-privileges`
- read-only application filesystem; small writable temporary filesystem for compilation
- no external network access (use an internal-only network if the instructor needs browser access)
- cgroup memory, CPU and PID limits
- seccomp/AppArmor profile and restricted filesystem mounts
- disposable workspace per grading batch; destroy it after reports are exported
- keep the host kernel and container runtime patched

The Streamlit app is not an isolation boundary by itself. The institution should provision and
validate the VM/container profile before grading real untrusted submissions. Do not describe
resource limits as secure containment.


## Optional Bubblewrap mode (final enhanced release)

On Linux, install Bubblewrap (`sudo apt install bubblewrap`) and set this in `rules/rules.json`:

```json
"execution": {
  "sandbox_mode": "bubblewrap"
}
```

When requested, the runner invokes Bubblewrap with a separate network namespace, read-only host filesystem view, writable per-test working directory, isolated process session, `/proc` and `/dev` mounts. If `bwrap` is missing, the runner fails closed and does not start the student executable. The default remains `off` for backward compatibility; enable it only after testing the exact lab host configuration.

This optional mode is defense-in-depth, not a claim of complete sandboxing. A production grader should additionally use a disposable non-root VM/container, cgroups for CPU/memory/PID limits, seccomp/AppArmor, no host secrets or Docker socket, and administrator-controlled mount/network policy. Bubblewrap availability and user-namespace policy vary across Linux distributions.
