# paperguard-example-plugin

A complete, installable plugin demonstrating how to extend PaperGuard with
your own detector.

## What it does

Provides one new detector `X1_ZERO_VARIANCE` that flags any numeric column
whose every entry is identical (zero variance). This is a trivial but
illustrative example.

## Install (from this directory)

```bash
pip install -e .
```

After install, PaperGuard's `DetectorRegistry().register_default()`
automatically picks it up via the `paperguard.detectors` entry-point group.

Verify:

```bash
paperguard list-detectors --format ids | grep X1
# Should print: X1_ZERO_VARIANCE
```

## How it works

`pyproject.toml`:

```toml
[project.entry-points."paperguard.detectors"]
zero_variance = "paperguard_example_plugin.detectors:ZeroVarianceDetector"
```

`paperguard_example_plugin/detectors.py` defines a `BaseDetector` subclass.

## Use this as a template

1. Copy the directory to a new repo `paperguard-yourname-plugin/`.
2. Rename the package and entry-point name.
3. Implement your `_detect()` method.
4. Publish to PyPI if desired.

See `../03_custom_detector.py` for the in-repo detector tutorial.
