# Source-grounded acceptance evaluation

Run `backend/.venv/bin/python evals/run_evals.py --sources data/sample_policies` from the repository root. Source filenames and SHA-256 hashes must match the supplied assignment PDFs. Without `--sources`, only annotated values and schema are checked; the report explicitly records that evidence was not checked.

The golden file contains manually reviewed facts and absence checks from the development samples. It is never loaded by the extraction runtime. Counts exclude the duplicate Liberty PDF. The evaluator checks normalized values, statuses and retained conditions, then separately verifies that every claimed field cites a quote on the correct source page. Citation support is not a semantic correctness proof, and this small development set does not estimate accuracy on unseen insurers.
