# Agent Development Guide

## Commands

- `pnpm dev` - Start all dev servers (web:3000, admin:3001)
- `pnpm build` - Build all packages and apps
- `pnpm check` - Run all checks (format, lint, types)
- `pnpm check:lint` - OxLint across all packages
- `pnpm check:types` - TypeScript type checking
- `pnpm fix` - Auto-fix format and lint issues
- `pnpm turbo run <command> --filter=<package>` - Target specific package/app

## Code Style

- **Imports**: Use `workspace:*` for internal packages, `catalog:` for external deps
- **TypeScript**: Strict mode enabled, all files must be typed
- **Formatting**: oxfmt, run `pnpm fix:format`
- **Linting**: OxLint with shared `.oxlintrc.json` config
- **Naming**: camelCase for variables/functions, PascalCase for components/types
- **Error Handling**: Use try-catch with proper error types, log errors appropriately
- **State Management**: MobX stores in `packages/shared-state`, reactive patterns
- **Testing**: All features require unit tests, use existing test framework per package
- **Components**: Primitives come from the published `@makeplane/propel` npm package (`@makeplane/propel/components/*`, `elements/*`, `icons`); composite/Plane-specific components live in `@plane/blocks` (`packages/blocks`, subpath imports only, e.g. `@plane/blocks/toast`)

## Feature flags

- **Registration**: Every new user-facing capability MUST have a `FeatureFlag` row in
  `apps/api/plane/billing` before or in the same change that introduces it. A capability with no
  flag cannot be gated per plan and cannot be priced per seat later. `has_feature()` had zero
  production callers until Phase 3 of the billing work — that is what "registered but unread"
  looks like.
- **limit_type**: Each flag declares `boolean`, `number` or `unlimited`. Choose `number` with a
  `unit_label` whenever the capability has a countable limit — a single global limit across flags
  does not work, because "5 charts" and "10 projects" are not the same constraint. A
  `limit_value` on a non-number flag is rejected by the serializer rather than silently dropped.
- **Gating**: Gate the capability with `has_feature(workspace, code)` from
  `plane.billing.services.entitlements`, and read a countable limit with
  `feature_limit(workspace, code)`. Do not read `PlanFeatureFlag` directly, and do not branch on
  `plan.code` — that couples the code to the plan catalogue.
- **Testing**: Gating needs a test that covers the off case, otherwise the flag silently does
  nothing. A flag whose limit is stored but never read is the same failure with a smaller blast
  radius.

See `docs/superpowers/specs/2026-10-07-billing-wallet-upgrade-design.md` for the design.

## Backend tests (Docker)

The Django/pytest suite for `apps/api` runs in an isolated stack defined by `docker-compose-test.yml` at the repo root.

Prereq (once): `./setup.sh` — generates `apps/api/.env` from `.env.example`.

- Full suite: `docker compose -f docker-compose-test.yml up --build --abort-on-container-exit --exit-code-from api-tests`
- Subset: `docker compose -f docker-compose-test.yml run --rm api-tests pytest -m unit`
- Teardown: `docker compose -f docker-compose-test.yml down -v`

See `apps/api/tests/RUNNING_TESTS.md` for the full walkthrough and troubleshooting; see `apps/api/tests/TESTING_GUIDE.md` for test conventions and fixtures.
