# Third-party notices

ASDR is MIT-licensed (see `LICENSE`). It adapts or refers to the work below.
Nothing listed here is bundled as code unless the entry says so.

## Ponytail — adapted (build ladder)

`templates/build-ladder.md` adapts the seven-rung "ladder" from
[DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail) v4.10.0.
The `asdr` marketplace also lists Ponytail as an optional plugin (disabled by
default, installed from its own repository).

```
MIT License

Copyright (c) 2026 DietrichGebert

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## UI UX Pro Max — not bundled

[nextlevelbuilder/ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill)
(MIT, Copyright (c) 2024 Next Level Builder) is installed from its own
repository as a dependency through the `asdr` marketplace, pinned by commit.
`scripts/uupm_design_system.py` calls its search script when it is present.

## AX — schema vocabulary only

`templates/agent-runtime.yaml` uses the field names of the AX `v1alpha1`
schema ([google/ax](https://github.com/google/ax), Apache License 2.0) as a
design vocabulary. No AX code is included.

## Test tooling — not bundled

The browser-test templates are written for Playwright (Apache-2.0), Cypress
(MIT), Selenium (Apache-2.0) and axe-core (MPL-2.0). Projects install them
with their own package managers; ASDR ships none of their code.
