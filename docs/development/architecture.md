# Backend Architecture

```text
backend/
  src/
    api/       FastAPI application, routes, and API-only schemas
    core/      Agent orchestration, domain agents, and domain schemas
    data/      Document extraction and retrieval
    models/    External AI model adapters
    utils/     Logging and other small helpers
    config.py  Typed JSON configuration loader
  config.json  Non-secret backend configuration
  tests/
    unit/
    integration/
    e2e/
  requirements/
    base.txt
    dev.txt
    prod.txt
```

Dependencies point inward: `api` calls `core`; `core` may use `data`, `models`,
and `utils`; configuration is read through `config.py` from `config.json`.
Secrets such as `OPENAI_API_KEY` are injected through the process environment.
