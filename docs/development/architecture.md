# Backend Architecture

```text
backend/
  src/
    api/       FastAPI application, routes, and API-only schemas
    core/      Agent orchestration, domain agents, and domain schemas
    data/      Document extraction and retrieval
    models/    External AI model adapters
    utils/     Logging and other small helpers
    config/    Environment-backed settings
  tests/
    unit/
    integration/
    e2e/
  requirements/
    base.txt
    dev.txt
    prod.txt
```

Dependencies point inward: `api` calls `core`; `core` may use `data`, `models`, and `utils`; configuration is read through `config.settings`.
