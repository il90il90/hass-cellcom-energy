# Test Fixtures

This directory contains sanitised JSON responses from the Cellcom API,
used as recorded fixtures for unit tests.

**All** files in this directory must be anonymised:
- Phone numbers → `0500000000`
- ID numbers → `000000000`
- Names → `Test User`
- Emails → `test@example.com`
- Addresses → `Test Street 1, Test City`
- BANs, meter numbers, contract numbers → `000000000`
- JWT tokens → `test_jwt_token`
- GUIDs → `00000000-0000-0000-0000-000000000000`

Never commit real personal data, even partially.
