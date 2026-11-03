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
- **Default Plan Availability**: Every new feature must be registered in the system's feature flags
  so its availability across financial/billing plans can be controlled. By default, it MUST be
  enabled across all plans, unless explicitly configured to be disabled for specific plans.
  - هر فیچر جدیدی که تولید می‌شود باید به فیچرفلگ‌های سیستم اضافه شود تا معلوم شود در کدام پلن‌های مالی قابل استفاده است و به‌صورت پیش‌فرض در تمامی پلن‌ها فعال باشد، مگر اینکه برای برخی پلن‌های مالی غیرفعال شود.
- **Developer Confirmation & Autonomous Mode**: When introducing a new feature, ask the developer
  whether this feature should be added to feature flags and whether it should be active by default
  across all plans. If the developer specifies autonomous mode (or asks to work autonomously),
  automatically register the feature in feature flags and enable it across all financial plans by default.
  - هنگام پیاده‌سازی هر فیچر جدید باید از توسعه‌دهنده پرسیده شود که آیا این فیچر به فیچرفلگ‌ها اضافه شود و در همهٔ پلن‌ها پیش‌فرض فعال باشد یا خیر؛ اما اگر برنامه‌نویس گفت کار به‌صورت autonomous (خودمختار) انجام شود، آن فیچر را به‌صورت پیش‌فرض به فیچرفلگ‌ها اضافه کرده و برای همهٔ پلن‌های مالی فعال کن.
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

## Backend dependencies (uv)

`apps/api` dependencies are managed with [uv](https://docs.astral.sh/uv/): declared in `apps/api/pyproject.toml`, pinned in `apps/api/uv.lock` (commit both). Groups: `dev` and `test` (installed by default; they use `psycopg-binary`), `production` (gunicorn + the source-built `psycopg-c`; production image and migration-check only). Lint config lives in `apps/api/ruff.toml`.

- uv must be exactly the `required-version` in `apps/api/pyproject.toml` (`uv self update <version>`); bump it together with the uv image in both Dockerfiles
- Set up a local env: `cd apps/api && uv sync`
- Inside the dev/test containers, always pass `--inexact` (`uv sync --inexact`): uv targets the image's system Python there, and an exact sync would uninstall pip
- Add/upgrade a dependency: `uv add <pkg>==<version>` (or `--group test`/`--group dev`), or edit `pyproject.toml` and run `uv lock`
- Run tools: `uv run python manage.py ...`, `uv run ruff check .`

## Backend tests (Docker)

The Django/pytest suite for `apps/api` runs in an isolated stack defined by `docker-compose-test.yml` at the repo root.

Prereq (once): `./setup.sh` — generates `apps/api/.env` from `.env.example`.

- Full suite: `docker compose -f docker-compose-test.yml up --build --abort-on-container-exit --exit-code-from api-tests`
- Subset: `docker compose -f docker-compose-test.yml run --rm --build api-tests pytest -m unit`
- Teardown: `docker compose -f docker-compose-test.yml down -v`

See `apps/api/tests/RUNNING_TESTS.md` for the full walkthrough and troubleshooting; see `apps/api/tests/TESTING_GUIDE.md` for test conventions and fixtures.

## Feature Delivery & Changelog

- **Changelist**: Whenever a feature is implemented or modified, document the changes in a clear changelist so it is transparent what was added, modified, or removed.
- **PO Rationale (Persian)**: Explain the reason for the changes (reflecting the Product Owner's requirement) in simple, concise Persian:
  - هر فیچری که تولید یا تغییر داده می‌شود، تغییرات باید در یک چنج‌لیست مشخص شود تا معلوم باشد چه بخش‌هایی تغییر کرده‌اند.
  - دلیل تغییرات (خواستهٔ PO) باید به زبان ساده، بسیار کوتاه و به زبان فارسی توضیح داده شود.


## Demo server deployment

- **`preview` is the main branch.** Every push or merge to `preview` triggers `.github/workflows/deploy-staging.yml`, which builds the images and redeploys the demo (staging) server on Dokploy.
- **Trigger phrase**: when the user says "روی سرور دمو بده" (deploy to the demo server), do the whole flow without asking:
  1. Commit every pending change on the current branch, with a Co-Authored-By line.
  2. Push the branch and merge it into `preview`. Push `preview` (`git push fork preview`, or `origin` if the user says so).
  3. Confirm that the "Deploy Staging" run for the new `preview` commit is queued or running, and wait for it to finish (`gh run list`).
  4. Report done only after the run succeeds. Name the commit and the run. If it fails, report the failure and do not call it done.
- Never push directly to `preview` without a merge from a feature branch unless the user asks for it.
