# MarkeTOB pilot bots

Two independent Python executables: `python -m marketob_bots.catalog` and
`python -m marketob_bots.news`. Each uses its own operational key and SQLite journal;
neither uses the platform database. See the English
[local setup](../../docs/setup/PILOT_BOTS.md) and [SDK guide](../../packages/bot-sdk/README.md).

Catalog goods and outcomes are synthetic. The configurable public RSS source is
real; `--offline` uses a bundled synthetic fixture. There are no financial operations.
