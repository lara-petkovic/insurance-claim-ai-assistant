# Demo claim dataset

This directory contains fictional policy wording and claim scenarios for manually testing the insurance-claim workflow. None of the policies, people, dates, or incidents are real.

## Contents

- `policies/`: five policy text files covering home, auto, and travel examples.
- `images/`: synthetic claim-evidence images generated for this project. They are test assets, not genuine loss evidence.
- `supporting_documents/`: fictional evidence files used by selected complete-claim scenarios.
- `claims.json`: claim descriptions, policy mappings, expected safety behavior, and optional image mappings.
- `run_demo_cases.py`: runs every case through the backend orchestrator.
- `results.md` and `results.json`: generated summaries from the latest batch run.

## Run all cases

From the repository root:

```powershell
$env:OPENAI_API_KEY='your_api_key_here'
& '.\backend\.venv\Scripts\python.exe' backend\demo_cases\run_demo_cases.py
```

The runner uses the configured text, planning, and vision models. Any unavailable model or invalid model response stops the run visibly rather than switching to deterministic fallback.

These examples are deliberately varied. Some are clearly covered or excluded, while conditional, ambiguous, and conflicting policy language should fail closed to human review.
