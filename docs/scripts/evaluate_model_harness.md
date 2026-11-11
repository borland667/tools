# Local model harness probe

`scripts/evaluate_model_harness.py` exercises an installed OpenCode CLI against
a configured loopback HTTP model. Python 3.9+ and OpenCode are required. Raw
Strata line transport needs a separate real HTTP server and is rejected here.

```bash
python3 scripts/evaluate_model_harness.py --help
python3 -B scripts/evaluate_model_harness.py \
  --config /path/to/private-pilot.json --engine local-candidate \
  --output /path/to/new-harness-results --timeout 180
```

The probe creates a disposable two-file workspace and asks a read-only reviewer
to read a known defective function and identify its faulty line. Separate XDG
config/data/cache/state directories preserve the user's normal installation.
The agent can read its fixture workspace; external-directory access, edits,
shell, web, skills and delegation are denied. This is application permission
control, not an operating-system sandbox. File hashes check workspace changes.

A loopback proxy independently enforces the selected model, three upstream
requests and at most 768 output tokens per request. An explicit session title
avoids an auxiliary title request competing for that budget. The child process
group has a wall timeout (maximum 300 seconds). Only test-owned processes stop.

The report records actual read successes, tool errors, final finding score,
unchanged files, raw events and proxy limits. A successful CLI exit alone is
insufficient; missing reads, wrong/missing findings, timeout or file mutation
return failure. Output format compliance is tracked separately from recovered
JSON semantics. This single probe does not qualify write-enabled coding,
arbitrary tools, background work or long-running agent loops.

Configuration follows the installed OpenCode 1.x-compatible schema. Tool and
permission formats can change; verify the installed version and inspect errors
before adapting it. Do not widen editing or external access just to pass a test.
See [the full pilot guide](evaluate_local_models.md) for corpus, resource and
interpretation limits.
