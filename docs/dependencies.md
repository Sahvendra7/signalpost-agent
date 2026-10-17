# Runtime dependencies that carry data

## Public suffix list

`website._registered_domain` (used for site identity, e-mail domains and refresh) needs the Public Suffix
List (PSL) to find the registered domain (for example `example.co.uk`).

| Item | Value |
| --- | --- |
| Source | The PSL snapshot bundled in the `tldextract` wheel (`tldextract/.tld_set_snapshot`) |
| Pinned version | `tldextract==5.3.2` (`pyproject.toml`, locked with hashes in `uv.lock`) |
| Snapshot | `VERSION: 2025-04-07_15-51-09_UTC`, `COMMIT: 5fc8d12c1624ddbc56a80e944aca151a8ee466a1`, SHA-256 `b69315c085d53972724b8f2df111ffc329b0c84fe0a47d62c8c91655cc774a38` (318,581 bytes) |
| Sections used | ICANN section only (`include_psl_private_domains=False`, as before) |
| Licences | PSL: Mozilla Public License 2.0. `tldextract`: BSD-3-Clause. |
| Network use | **None.** `TLDExtract(suffix_list_urls=(), cache_dir=None, fallback_to_snapshot=True)`: no request to publicsuffix.org or GitHub, and nothing is written to `~/.cache`. |

The default `tldextract.extract()` downloads the live list on first use and caches it. With sockets blocked it
was measured making 2 attempts (publicsuffix.org, then raw.githubusercontent.com). The pinned extractor makes
0 attempts, and `tests/test_public_suffix.py` checks that with sockets blocked and a fresh `HOME`.

**How to update the list:**

1. Bump `tldextract` in `pyproject.toml`.
2. Run `uv lock --upgrade-package tldextract`.
3. Update the version line, commit line and SHA-256 above and in `tests/test_public_suffix.py`.
4. Run the full test suite.

A newer snapshot can change a registered domain only for suffixes added since 2025-04-07. Norwegian
`.no` second-level suffixes have not changed in that period.

## Other data carried by dependencies

No other dependency downloads data at run time on the batch path. The remaining network use is the declared
sources: Brreg APIs and company websites (`docs/official-source-compliance.md`).
