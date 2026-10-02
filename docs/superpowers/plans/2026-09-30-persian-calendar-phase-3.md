# Persian Calendar — Phase 3 (Long Tail) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every remaining user-visible date in `apps/web` renders in the user's chosen calendar.

**Architecture:** Mechanical, not novel. Each call site gains a `calendarSystem` argument supplied by `useUserProfile()`, which ~50 components already import. No new component, no new abstraction, no API change.

**Tech Stack:** TypeScript, `useUserProfile` from `@/hooks/store/user`, the existing calendar-aware formatters in `packages/utils/src/datetime.ts`.

## What phase 3 originally was, and why this replaced it

The design spec's phase 3 was "relative filter boundaries + Persian email dates". Investigation showed **both targets are empty in this fork**:

- **Analytics relative filters are disabled.** All five web call sites have `date_filter` commented out (`apps/web/components/analytics/overview/project-insights.tsx:45` and four others), and so is the entire `DurationDropdown` (`analytics-filter-actions.tsx:27-34`). `get_analytics_filters` (`apps/api/plane/utils/date_utils.py:182`) does not even accept `start_date`/`end_date`, so the `custom` slug the spec planned to reuse returns `None` — no filtering at all, silently.
- **Emails render no date.** `email_notification_task.py:221` reduces `activity_time` to `"%H:%M %p"` — time only, calendar-invariant. The one visible date is a raw ISO `YYYY-MM-DD` due-date value printed at `templates/emails/notifications/issue-updates.html:80`.

There is nothing calendar-aware to fix in either. Re-enabling a disabled analytics feature is a separate product decision with an API change; it was rejected in favour of this.

**What is left is 74 unmigrated call sites across ~45 files** — `renderFormattedDate`, `renderFormattedDateWithoutYear`, `calculateTimeAgo`, `formatDateRange`. These _are_ user-visible and _are_ still Gregorian. This plan connects them.

## Global Constraints

- **The Gregorian path must stay byte-identical.** Every one of these functions defaults to `"gregorian"`, so a missed site is a bug and an incorrect one is a regression. Both are caught by the same check.
- **`apps/web` has no test runner** — no `test` script, no vitest dependency, zero test files. Every test lives in `packages/calendar/tests/` and pins behaviour there; the web call sites are verified by typecheck plus the manual QA list.
- **`useUserProfile()` returns the store; `calendarSystem` is a narrowed getter** on `IUserProfileStore`. Many files already destructure `{ data: userProfile }` — in those, `userProfile.calendar_system` is the value already in hand. Where that is used, prefer it over adding a second hook call.
- **Do not add a dependency to any `package.json`.**
- **Do not change `renderFormattedDate` or friends.** They are correct and pinned.
- **`renderFormattedTime` is NOT in scope.** It renders a wall-clock time, which is calendar-invariant. Leave every one alone.
- **Components that render inside a `tooltip`/`label` string need the system threaded into the template**, not just the visible child.

## Two patterns, and the trap in the second

**Pattern A — the file already has the value:**

```tsx
const { data: userProfile } = useUserProfile();
… renderFormattedDate(x, undefined, userProfile.calendar_system)
```

**Pattern B — the file must add the hook:**

```tsx
import { useUserProfile } from "@/hooks/store/user";
…
const { calendarSystem } = useUserProfile();
… calculateTimeAgo(x, calendarSystem)
```

**The trap: `renderFormattedDate`'s second parameter is the format token, not the system.** A naive edit turns

```tsx
renderFormattedDate(date); // "Jun 15, 2025"
```

into

```tsx
renderFormattedDate(date, calendarSystem); // calendarSystem passed as the TOKEN
```

That does not throw — `date-fns` renders literal `g`, `r`, `o`, … — so it ships silently as garbage text. **When the token is absent you must pass `undefined` explicitly.** `renderFormattedDateWithoutYear(date, system)` and `calculateTimeAgo(time, system)` take the system as their _second_ argument, so those are the easier two. Grep for `renderFormattedDate(` and check every one.

---

## Task 1: Activity, comments, and notification surfaces

**Files:**

- `apps/web/components/comments/card/display.tsx:127,133`
- `apps/web/components/common/activity/activity-block.tsx:49,53`
- `apps/web/components/issues/issue-detail/issue-activity/activity/actions/helpers/activity-block.tsx:55,58`
- `apps/web/components/profile/activity/activity-list.tsx:77,168`
- `apps/web/components/profile/overview/activity.tsx:80`
- `apps/web/components/core/activity.tsx:687,719`
- `apps/web/components/core/description-versions/dropdown.tsx:61`, `dropdown-item.tsx:42`, `modal.tsx:118`
- `apps/web/components/workspace-notifications/sidebar/notification-card/item.tsx:130,136`
- `apps/web/components/workspace-notifications/sidebar/notification-card/content.tsx:62,67`

**Interfaces:**

- Consumes: `useUserProfile` (Pattern B for all of these — none import it today)
- Produces: no new exports.

- [ ] **Step 1: Confirm none of these already import the hook**

```bash
cd apps/web/components
for f in comments/card/display.tsx common/activity/activity-block.tsx \
  issues/issue-detail/issue-activity/activity/actions/helpers/activity-block.tsx \
  profile/activity/activity-list.tsx profile/overview/activity.tsx core/activity.tsx \
  core/description-versions/dropdown.tsx core/description-versions/dropdown-item.tsx \
  core/description-versions/modal.tsx \
  workspace-notifications/sidebar/notification-card/item.tsx \
  workspace-notifications/sidebar/notification-card/content.tsx; do
  printf "%-72s %s\n" "$f" "$(grep -c useUserProfile "$f")"
done
```

Any file showing a non-zero count uses Pattern A instead.

- [ ] **Step 2: Add the hook and thread the system**

For each file, add the import and the destructure, then fix both call shapes:

```tsx
// calculateTimeAgo takes the system second — straightforward
{calculateTimeAgo(activity.created_at, calendarSystem)}

// renderFormattedDate takes a TOKEN second — undefined is mandatory
label={`${renderFormattedDate(comment.created_at, undefined, calendarSystem)} at ${renderFormattedTime(comment.created_at)}`}
```

`core/activity.tsx:687,719` render `activity.new_value` for date-field changes — the same form.

**Do not touch `renderFormattedTime`.** It is on lines 127 and 49 of the two `activity-block` files and renders a clock time.

- [ ] **Step 3: Check the files are `observer`s**

`workspace-notifications/.../notification-card/content.tsx` builds a `value:` property consumed by a parent. If the component reads the store but is not wrapped in `observer`, it will not re-render when the async profile load lands and will keep showing Gregorian — the same bug phase 2 found in `progress-chart.tsx`. Check each file for `observer(`; add it only where a store read is genuinely new.

- [ ] **Step 4: Verify the argument-order trap was avoided**

```bash
cd /Volumes/OWC/projectsOWC/github/plane
grep -rn "renderFormattedDate([a-zA-Z_.?]*," apps/web/components/comments apps/web/components/common/activity \
  apps/web/components/profile apps/web/components/core apps/web/components/workspace-notifications \
  | grep -v "undefined\|calendarSystem\|system"
```

Expected: **no output**. Any hit passes `calendarSystem` into the token slot.

- [ ] **Step 5: Verify**

Run: `npx turbo run check:types` → 28/28
Run: `pnpm --filter=@plane/blocks test` → 277
Run: `npx turbo run check:lint` → 16/16

- [ ] **Step 6: Commit**

```bash
git add apps/web/components
git commit -m "feat(web): render activity and notification dates in the user's calendar"
```

---

## Task 2: Issue detail, layout, and spreadsheet surfaces

**Files:**

- `apps/web/components/issues/issue-layouts/utils.tsx:742,745,749`
- `apps/web/components/issues/preview-card/date.tsx:36,42,51`
- `apps/web/components/issues/issue-layouts/spreadsheet/columns/created-on-column.tsx:24`
- `apps/web/components/issues/issue-layouts/spreadsheet/columns/updated-on-column.tsx:24`
- `apps/web/components/issues/issue-detail/issue-activity/activity/actions/target_date.tsx:38`
- `apps/web/components/issues/issue-detail/issue-activity/activity/actions/start_date.tsx:38`
- `apps/web/components/issues/issue-detail/links/link-detail.tsx:114`, `link-item.tsx:85`
- `apps/web/components/issues/attachment/attachment-detail.tsx:85`, `attachment-list-item.tsx:82`

**Interfaces:**

- Consumes: `useUserProfile`
- Produces: no new exports.

- [ ] **Step 1: Determine the pattern per file**

`created-on-column.tsx` and `updated-on-column.tsx` live beside `due-date-column.tsx` and `start-date-column.tsx`, which **already** import `useUserProfile` (lines 17 and 16) and already read `userProfile.calendar_system`. Use Pattern A there.

The rest are standalone — Pattern B.

- [ ] **Step 2: Handle the label-bearing call sites**

`issues/issue-layouts/utils.tsx:742-749` builds dropdown labels:

```
`From ${renderFormattedDate(block.start_date)}`
`Till ${renderFormattedDate(block.target_date)}`
`${renderFormattedDate(block?.start_date)} to ${renderFormattedDate(block?.target_date)}`
```

Thread the system into each interpolation — a label rendered in the wrong calendar is as visible as one rendered in the body.

The two `attachment-*` files build `uploaded on ${...}` inside a template. Same treatment.

- [ ] **Step 3: Verify**

Run: `npx turbo run check:types` → 28/28
Run: `pnpm --filter=@plane/blocks test` → 277

- [ ] **Step 4: Commit**

```bash
git add apps/web/components/issues
git commit -m "feat(web): render issue detail dates in the user's calendar"
```

---

## Task 3: List, card, and stat surfaces

**Files:**

- `apps/web/components/project/form.tsx:466`
- `apps/web/components/project/card.tsx:297`
- `apps/web/components/project/applied-filters/date.tsx:35`
- `apps/web/components/cycles/active-cycle/cycle-stats.tsx:158,162`
- `apps/web/components/cycles/applied-filters/date.tsx:35`
- `apps/web/components/modules/applied-filters/date.tsx:36`
- `apps/web/components/modules/links/list-item.tsx:102`
- `apps/web/components/common/applied-filters/date.tsx:35`
- `apps/web/components/inbox/inbox-filter/applied-filters/date.tsx:32`
- `apps/web/components/issues/issue-layouts/filters/applied-filters/date.tsx:35`
- `apps/web/components/inbox/sidebar/inbox-list-item.tsx:85,86`
- `apps/web/components/exporter/column.tsx:51`, `single-export.tsx:61`
- `apps/web/components/profile/sidebar.tsx:65`

**Interfaces:**

- Consumes: `useUserProfile`
- Produces: no new exports.

- [ ] **Step 1: Migrate the five `applied-filters/date.tsx` files as one change**

These are near-duplicates — all build `` `${capitalizeFirstLetter(time)} ${renderFormattedDate(date)}` ``. Do them together so they stay consistent, and so a reviewer can diff them against each other.

Note `inbox-filter/applied-filters/date.tsx:32` also does its own `charAt(0).toUpperCase()` on the date's month name. That capitalisation is a no-op for Persian (no case) and must be left alone — it is not calendar logic.

- [ ] **Step 2: Migrate the rest with Pattern B**

`cycle-stats.tsx:158` puts a date inside a `Tooltip` label and `:162` renders the visible `renderFormattedDateWithoutYear`. Both need it — a correct visible value with a wrong tooltip is a half-fix.

`exporter/column.tsx:51` renders a date in the **export history table**, which is a table in the app UI (not the downloaded file). That one is in scope; the file contents themselves stay Gregorian, which is a separate deliberate decision already documented in the spec.

- [ ] **Step 3: Verify**

Run: `npx turbo run check:types` → 28/28

- [ ] **Step 4: Commit**

```bash
git add apps/web/components
git commit -m "feat(web): render list and card dates in the user's calendar"
```

---

## Task 4: Home, pages, settings, and API tokens

**Files:**

- `apps/web/components/home/widgets/recents/page.tsx:63`, `project.tsx:48`, `issue.tsx:97`
- `apps/web/components/home/widgets/links/link-item-block.tsx:46`
- `apps/web/components/pages/header/archived-badge.tsx:24`
- `apps/web/components/pages/version/main-content.tsx:112`
- `apps/web/components/pages/list/block-item-action.tsx:64`
- `apps/web/components/pages/navigation-pane/tab-panels/info/version-history.tsx:61`
- `apps/web/components/pages/navigation-pane/tab-panels/info/actors-info.tsx:67`
- `apps/web/components/workspace/settings/useMemberColumns.tsx:126`
- `apps/web/components/projects/settings/useProjectColumns.tsx:134`
- `apps/web/components/api-token/modal/form.tsx:249,252`
- `apps/web/components/api-token/modal/generated-token-details.tsx:71`
- `apps/web/components/api-token/modal/create-token-modal.tsx:48`
- `apps/web/components/api-token/token-list-item.tsx:58,60`
- `apps/web/components/gantt-chart/helpers/add-block.tsx:91`
- `apps/web/components/gantt-chart/helpers/blockResizables/left-resizable.tsx:32`, `right-resizable.tsx:32`
- `apps/web/components/core/filters/date-filter-modal.tsx:170,172`
- `apps/web/components/dropdowns/merged-date.tsx:32`
- `apps/web/components/readonly/date.tsx:25`

**Interfaces:**

- Consumes: `useUserProfile`
- Produces: no new exports.

- [ ] **Step 1: Pattern A where the hook already exists**

`api-token/modal/form.tsx:107` and `core/filters/date-filter-modal.tsx:52` **already** destructure `{ data: userProfile }` — they pass `userProfile.calendar_system` to the picker today. Use `userProfile.calendar_system` for their remaining call sites rather than adding a second hook call.

`gantt-chart/chart/views/week.tsx:21` also already has it, but the three `gantt-chart/helpers/` files are standalone.

- [ ] **Step 2: `merged-date.tsx` takes `formatDateRange`, which is third-parameter**

```tsx
const displayText = formatDateRange(parsedStartDate, parsedEndDate, calendarSystem);
```

Not second — check the signature before editing.

- [ ] **Step 3: `readonly/date.tsx` — check whether it should take a prop instead**

It renders a read-only date display and already accepts a `formatToken` prop. If its callers are few and all know the user's calendar, a prop may be cleaner than a hook — but a hook is the consistent choice and matches every other site. Read the callers, then choose and justify it in the report.

- [ ] **Step 4: Verify**

Run: `npx turbo run check:types` → 28/28
Run: `pnpm --filter=@plane/blocks test` → 277

- [ ] **Step 5: Commit**

```bash
git add apps/web/components
git commit -m "feat(web): render remaining user-visible dates in the user's calendar"
```

---

## Task 5: Phase gate

**Files:**

- No new files.

- [ ] **Step 1: Prove no call site was missed**

```bash
cd /Volumes/OWC/projectsOWC/github/plane
grep -rn "renderFormattedDate(\|renderFormattedDateWithoutYear(\|calculateTimeAgo(\|formatDateRange(" \
  apps/web --include=*.tsx | grep -v "function \|export \|calendarSystem\|system)"
```

Expected: **no output**. Every remaining hit should pass a system.

- [ ] **Step 2: Prove no call site got the argument in the wrong slot**

```bash
grep -rn "renderFormattedDate([^)]*calendarSystem" apps/web --include=*.tsx | grep -v "undefined"
```

Expected: **no output** — every `renderFormattedDate` that passes `calendarSystem` must pass `undefined`
in the token slot first.

- [ ] **Step 3: Run every suite**

```bash
pnpm --filter=@plane/calendar test   # expect 121
pnpm --filter=@plane/blocks test     # expect 277
pnpm --filter=@plane/services test   # expect 13
npx turbo run check:types            # expect 28/28
npx turbo run check:lint             # expect 16/16
npx turbo run build --filter=web     # expect 11/11 — NOT --dry; phase 1 shipped a real build
                                        break that only --dry failed to catch
```

- [ ] **Step 4: Backend regression check**

Phase 3 touches no Python, but confirm:

```bash
cd apps/api
export DATABASE_URL="postgresql://plane:plane@localhost:55432/plane"
export REDIS_URL="redis://localhost:56379/0"
export DJANGO_SETTINGS_MODULE="plane.settings.test"
export SECRET_KEY="test-secret-key"
/tmp/api312/bin/python -m pytest -m unit -q --no-header -p no:cacheprovider   # expect 432
```

- [ ] **Step 5: Manual QA with a Persian profile**

Set `calendar_system: persian`, then walk every surface in Tasks 1–4. For each, confirm **both** that
the Persian rendering appears **and** that switching to Gregorian restores today's exact string:

- [ ] Activity feed: "3 hours ago", comment timestamps, version history
- [ ] Issue detail: start/due dates, "From … to …" cycle labels, attachments ("uploaded on")
- [ ] Issue list: created-on / updated-on spreadsheet columns, preview cards
- [ ] Applied-filter chips on projects, cycles, modules, issues, inbox
- [ ] Project card/form "Created on", inbox "Created on", cycle stats tooltips
- [ ] API tokens: expiry dates and "Expired … ago"
- [ ] Gantt bar tooltips
- [ ] Export history table
- [ ] Pages: archived badge, "Added by", member/project "joining date"
- [ ] Date filter modal summary, merged date dropdown
- [ ] **Confirm no English date appears anywhere on a Persian profile** — a single `Jun 15` next to a
      `۲۵ خرداد` means a missed call site

- [ ] **Step 6: Commit any QA fixes**

```bash
git add -A apps/web
git commit -m "fix(web): address phase 3 QA findings"
```

Skip if clean.

---

## Known gaps left open

- **`renderFormattedTime` is untouched by design.** It renders a wall-clock time, which has no
  calendar. Every call site that pairs it with a date now shows a Persian date and a neutral clock.
- **Backend-rendered dates are untouched**: email (`%H:%M %p`, calendar-invariant), exports
  (machine-consumed, deliberately Gregorian), activity-log values stored as raw ISO strings.
- **Analytics relative filters remain disabled.** Re-enabling them is a product decision with an
  API change, explicitly out of scope here.
- **`getWeekOfMonth` in `chart/utils.ts:52` is still a Gregorian week number** paired with a Persian
  month name. Only reachable if `x_axis_date_grouping` is ever passed, which no caller does.
- **`calculateTimeAgo`'s Persian path uses fixed-second thresholds** (month = 30 days), so "one
  month ago" is approximate rather than a true Persian month.
- **`fa-IR` translation and RTL** — phase 4.
