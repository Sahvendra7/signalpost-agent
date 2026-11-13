Clean-room checks: fresh `git clone`, checkout of the commit, empty UV_CACHE_DIR, `uv sync --locked`, full suite
(`uv run --with pytest python -m pytest -q -p no:cacheprovider`), then the documented batch command on 987832827.

38ff24c (final code): uv sync exit 0; 570 passed, 193 subtests passed; documented command exit 0.
fef9be4 (code 7a88046): uv sync exit 0; 568 passed, 193 subtests passed; documented command exit 0.
8b119ef (code 44d0cd3 minus the careers board rule): uv sync exit 0; 563 passed, 190 subtests passed.
