# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] — TBD

### Added
- Initial release
- Three-step OTP config flow (phone → SMS → ID number)
- 8 sensors: current bill, monthly kWh, meter number, tariff plan,
  total due, next bill date, customer info, token expiry
- 1 binary sensor: has outstanding bill
- Hebrew and English UI translations
- Rich entity attributes exposing all raw Cellcom API fields
- Automatic token refresh with HA reauth fallback
- HACS compatibility
