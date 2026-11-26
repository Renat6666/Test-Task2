"""The reporting app has no models on purpose.

Every figure it serves is aggregated from the transaction ledger at read time
(see ``apps.reports.selectors``) and cached in Redis, never stored in a table.
"""
