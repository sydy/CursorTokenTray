# Native ports

Golden JSON fixtures shared by Python, Swift (`macos/`), and C# (`windows/`).

- `usage_summary_cases.json` — Dashboard usage-summary payloads and expected snapshots
- `token_cases.json` — WorkosCursorSessionToken normalize / variants / account id
- `format_cases.json` — membership, USD, token count, status pill / plan caption
- `aggregated_usage_cases.json` — model token aggregation

Python tests in `tests/test_fixtures.py` lock these to the historical parser.
Swift and C# unit tests load the same files so both native ports stay aligned.
