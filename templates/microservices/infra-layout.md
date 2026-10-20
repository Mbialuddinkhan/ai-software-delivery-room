# Infrastructure layout (ASDR 3.8)

Terraform or OpenTofu for every cloud; one module per building block and
cloud, composed per environment. devops writes it from docs/03d-portability.md.

```
infra/
  modules/
    relational-db/aws/      relational-db/azure/      relational-db/gcp/
    events/aws/             events/azure/             events/gcp/
    containers/aws/         containers/azure/         containers/gcp/
    …one folder per building block the product uses × production cloud
  envs/
    test-<cloud>/           the temporary test environment (the cloud chosen at the start)
      main.tf               composes the modules; every resource tagged
      variables.tf          region, name prefix, ttl, budget
    staging-<cloud>/  prod-<cloud>/   written, never applied by ASDR
  local/
    otel-collector.yaml     local observability config used by docker compose
```

Rules for the test environment:

- Tagged on every resource: `owner`, `purpose = asdr-test`, `project`,
  `expires = <created + ttl>`; a budget alert at `budget_usd_per_day`.
- Created only after the user approves (cloud_env.py create --approved-by …),
  destroyed with `terraform destroy` as soon as the cloud test run and
  cloud_parity.py are done (cloud_env.py destroyed …). The release gate refuses
  while one is still running.
- Deployed with the least-privilege role named in .harness/cloud.json, signed
  in through the cloud's own CLI. No keys in files, state with no secrets in
  outputs.
- `cloud_preflight.py` (init, validate, fmt, checkov when installed) must be
  READY before any apply; plan output is shown to the user with the approval
  question.
- staging and production are written and validated, never applied by ASDR.
