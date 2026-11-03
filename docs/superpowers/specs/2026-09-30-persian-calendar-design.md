# Persian (Jalali) Calendar Support — Design Spec

**Date:** 2026-09-30
**Status:** Approved
**Scope:** Phases 1–3 (calendar core, calendar views, relative boundaries). Phase 4 (fa-IR translation + RTL) is a separate project.

---

## Goal

Every date the product displays uses the user's chosen calendar. New Persian-speaking users see the Persian (Jalali / Shamsi) calendar.

**Storage never changes.** All dates stay Gregorian (ISO / `Date` / `datetime`) in the database, the API payloads, and every existing filter and query. Only the presentation layer is added.

## Non-goals

- Replacing `date-fns` as the repo's date library.
- Storing Jalali strings in the database.
- Translating the UI into Persian (phase 4) or laying out the app RTL (phase 4).
- Translating email body copy (only the dates in emails change).
- Changing export file contents (see [§8.4](#84-exports)).

## Approach

**Thin display layer.** A `CalendarAdapter` interface with two implementations — `GregorianCalendar` (current behavior) and `PersianCalendar` (native `Intl`). All display code talks to the adapter, never to raw `Date` arithmetic, when it needs calendar-aware behaviour. `Date` values stay Gregorian everywhere.

### Why an adapter rather than a Jalali library

Adding `dayjs-jalali` or `jalaali-js` would mean replacing `date-fns` across ~18 importing files and reconciling three different date APIs simultaneously. The adapter keeps `date-fns` in place for everything that is genuinely arithmetic (differences, ranges, filters) and confines calendar knowledge to one new package.

### Why native `Intl` rather than hand-rolled conversion

Modern browsers implement the Persian calendar via `Intl.DateTimeFormat`'s `calendar: 'persian'` option, backed by Unicode CLDR. The conversion tables are maintained upstream and are exact for Persian years 1178–1633. Hand-rolling risks an off-by-one somewhere that is very hard to notice and very visible to users.

---

## 1. Phase 1 — Calendar core

### 1.1 New package: `@plane/calendar`

A standalone package in `packages/calendar`, separate from `packages/utils` because the calendar logic is self-contained, needs its own tests, and should not drag `date-fns` consumers into it.

```
packages/calendar/
  package.json
  vitest.config.ts
  src/
    types.ts                    CalendarSystem, CalendarDateParts, CalendarAdapter, FormatOptions
    adapters/
      gregorian.ts
      persian.ts
    picker/
      calendar-surface.tsx      picks the right month grid
      persian-month-grid.tsx
      month-year-picker.tsx
      day-cell.tsx
      use-calendar-navigation.ts
    index.ts
  tests/
```

#### The adapter contract

| Method | In | Out | Purpose |
|---|---|---|---|
| `getSystem()` | — | `'gregorian' \| 'persian'` | Identity |
| `toParts(date)` | `Date` | `{year, month, day}` | Gregorian `Date` → parts in the active calendar |
| `fromParts(y, m, d)` | numbers | **Gregorian `Date`** | Inverse. The critical method. |
| `getMonthLength(y, m)` | numbers | `28..31` | Grid construction |
| `getMonthGrid(y, m, weekStartsOn)` | numbers | `Date[]` (42 entries) | Month grid with leading/trailing padding |
| `addMonths(y, m, delta)` | numbers | `{year, month}` | Navigation without `Date` |
| `format(date, opts)` | `Date` | `string` | Display |
| `getMonthNames(style)` | — | `string[12]` | Month labels |
| `getWeekdayNames(style, weekStartsOn)` | — | `string[7]` | Weekday labels |

#### `fromParts` — the inverse conversion

Native `Intl` converts Gregorian → Persian but not the reverse, so `fromParts` is implemented as a **progressive search**:

1. Build an initial guess by substituting each Persian month `m` with Gregorian month `m` in the given Persian year.
2. Measure the guess with `toParts`, compute the per-month offset.
3. Apply the offset and re-measure. Repeat 3–5 times, or until `toParts(guess)` equals the requested parts.
4. Return the Gregorian `Date` for the converged day.

Results are memoized in a `Map` keyed by `year:month:day`. Converting the same date twice is free; the miss path costs a handful of `Intl` calls, which is fast enough for a user-driven picker.

The search terminates because `toParts` is monotonic in the Gregorian day and the offset shrinks each iteration. A residual-offset assertion in the implementation guards against a bad browser implementation returning nonsense.

#### `getMonthGrid`

Returns exactly 42 `Date` entries (6 weeks × 7 days) so the grid height never changes between months. Leading and trailing days from the adjacent months are included and rendered at reduced opacity, which is standard picker behavior and means the existing calendar layout's fixed row count survives unchanged.

### 1.2 Data model

```python
# apps/api/plane/db/models/user.py → Profile

class CalendarSystem(models.TextChoices):
    GREGORIAN = "gregorian", "Gregorian"
    PERSIAN = "persian", "Persian"

calendar_system = models.CharField(
    max_length=16,
    choices=CalendarSystem.choices,
    default=CalendarSystem.GREGORIAN,
)
```

- `ProfileSerializer` uses `fields = "__all__"`, so the field is exposed with no serializer change.
- A migration is added under `apps/api/plane/db/migrations/`, following the precedent of `0094_auto_20250425_0902.py` which added `start_of_the_week`.
- `packages/types/src/users.ts` → add `calendar_system: ECalendarSystem` to `TUserProfile` (line 62), with a new `export enum ECalendarSystem` placed next to the existing `EStartOfTheWeek` (line 15), matching the file's convention.
- `apps/web/store/user/profile.store.ts` → expose a `calendarSystem` getter alongside the existing derived values.

#### Default derived from language

At `Profile` creation, if `user.language` starts with `fa`, `calendar_system` is set to `persian`; otherwise `gregorian`.

This applies **only at creation time**. If a user later switches the interface language to Persian without having set the calendar explicitly, the calendar is left alone. Silently changing how dates render is disruptive, and the setting is a separate field precisely so the two can diverge.

When phase 4 lands and a real `fa` locale exists, a one-time prompt can offer to switch the calendar. That is out of scope here.

### 1.3 `packages/utils` integration

Existing function signatures in `packages/utils/src/datetime.ts` are **preserved**. The calendar system is an optional trailing parameter that defaults to Gregorian, so no existing call site breaks:

```ts
renderFormattedDate(date, formatToken?, system?)   // signature extended, existing calls unaffected
calculateTimeAgo(time, system?)                    // now uses Intl.RelativeTimeFormat
formatDateRange(start, end, system?)               // e.g. "۱۶ شهریور – ۲۲ شهریور ۱۴۰۳"
renderFormattedPayloadDate(date)                    // UNCHANGED — always "yyyy-MM-dd" Gregorian
```

`renderFormattedPayloadDate` is the API/persistence format and must not be localized. This is the boundary that keeps storage Gregorian.

New exports: `getCalendarAdapter(system)`, `toCalendarParts(date, system)`, `formatRelativeTime(date, system)`.

`apps/space/helpers/date-time.helper.ts` is a separate copy of three of these helpers for the public space app. It is updated to delegate to `@plane/calendar` rather than keep a third implementation.

### 1.4 Fixing the hardcoded-locale leaks

These three sites bypass the adapter entirely and must be routed through it, or Persian users will see mixed calendars on the same screen.

| File | Problem | Fix |
|---|---|---|
| `packages/constants/src/calendar.ts` | `MONTHS_LIST` / `DAYS_LIST` are fixed English arrays, consumed by the calendar layout's header, day tiles, and month dropdown | Remove the constants; consumers call `adapter.getMonthNames()` / `getWeekdayNames()` |
| `apps/web/components/profile/time.tsx` | `Intl.DateTimeFormat` pinned to `"en-US"` | Take the locale from the profile's language and the calendar from `calendar_system` |
| `apps/web/components/user/user-greetings.tsx` and `apps/web/components/home/user-greetings.tsx` | Four `Intl` calls pinned to `"en-US"` across two near-identical files | Route through the adapter; these two files should be consolidated into one shared helper while in there |

Also audited during phase 1: the 18 files that import `date-fns` directly. Most use it for arithmetic (differences, `addDays`, `startOfWeek`) and correctly need no change. The ones that format for display — `packages/blocks/src/property-select/date-select.tsx`, `date-range-select.tsx`, `apps/web/components/chart/utils.ts`, `packages/utils/src/cycle.ts`, `packages/utils/src/distribution-update.ts` — are switched to the adapter.

### 1.5 Persian date picker

#### Architecture

`DateSelect` and `DateRangeSelect` keep `DateSelectShell` untouched — it already owns the trigger, popover, and clear footer, and its `formatToken` / `weekStartsOn` props pass through cleanly. Only the popover's children change.

```
DateSelect / DateRangeSelect
  └── DateSelectShell          (unchanged)
        └── CalendarSurface    (new — picks a grid)
              ├── GregorianMonthGrid   (wraps propel's Calendar, unchanged behaviour)
              └── PersianMonthGrid     (new)
```

The Gregorian path keeps using `react-day-picker` through `@makeplane/propel/components/calendar`. **This means the 21 existing locales have zero behavioural change** — no regression surface at all on the default path.

#### `PersianMonthGrid` behaviour

- 6 rows × 7 columns = 42 cells, always
- `weekStartsOn` comes from `Profile.start_of_the_week`; Saturday is the Persian convention but the user's setting wins
- Single mode: click picks a day. Range mode: the first click sets the start, the second sets the end.
- Range selection mirrors the existing `date-range-select.tsx` draft pattern (`setDraft` / `shown = draft ?? value`): a `draft` range state shown while incomplete, committed on the second click, with the draft cleared when the popover closes.
- Navigation: `‹` / `›` step one Persian month; a year + month dropdown jumps directly
- Keyboard: arrows move by day, `PageUp`/`PageDown` by month, `Home`/`End` to week bounds, `Enter` selects, `Esc` closes
- `minDate` / `maxDate` / `disabled` behave exactly as `buildDisabledMatchers` already defines them

#### Accessibility contract

Each day cell's `aria-label` is produced by `adapter.format(date, { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })`. In Gregorian mode this emits the same English strings react-day-picker emits today, so the existing tests in `packages/blocks/src/property-select/date-select.test.tsx` — which query by accessible name like *"Sunday, June 15th, 2025"* — pass unchanged. The Persian grid emits the equivalent Persian strings, and new tests assert against those.

#### Prop plumbing

`packages/blocks` must not depend on `apps/web`, so `calendar_system` arrives as a prop. This mirrors how `weekStartsOn` already works: the ~25 call sites that pass `weekStartsOn={userProfile?.start_of_the_week}` from a wrapper in `apps/web` gain `calendarSystem` the same way, and a single shared wrapper reads both from the profile store. The four direct `Calendar` consumers — `date-select.tsx`, `date-range-select.tsx`, `apps/web/components/core/filters/date-filter-modal.tsx`, and `apps/web/components/inbox/modals/snooze-issue-modal.tsx` — switch to `CalendarSurface`.

### 1.6 Settings UI

In `apps/web/components/settings/profile/content/pages/preferences/language-and-timezone-list.tsx`, a new row after Language and before Start of the Week:

- A radio group or segmented control with two options, **not** a dropdown — there are only two choices and comparing them is the point.
- Wired through `updateUserProfile({ calendar_system })`, the same call the existing `StartOfWeekPreference` uses.
- MobX reactivity means the whole app re-renders in place; no reload.
- A short explanatory line under the control: "Dates are stored in Gregorian format and displayed in your chosen calendar."

New keys in the `common` namespace: `calendar`, `calendar_persian`, `calendar_gregorian`, and the description string. These are English-only until phase 4, since no `fa` locale exists yet.

The command palette (`apps/web/components/power-k/config/preferences-commands.ts`) gains an `update_calendar_system` command alongside the existing `update_start_of_week` and `update_interface_language`, for consistency with how every other profile preference is reachable.

---

## 2. Phase 2 — Calendar views

### 2.1 Issue calendar layout

A correction to the original assumption: the grid does **not** need restructuring. The layout already uses a fixed 6-row grid, and Persian months are at most 31 days (the first six months of the Persian year), so the row count is unchanged. What changes is the content and the navigation arithmetic.

1. `MONTHS_LIST` / `DAYS_LIST` — resolved in phase 1; the layout's header, day tiles, week header, and month dropdown read from the adapter. Note `MONTHS_LIST` is currently a **1-based object** (`MONTHS_LIST[getMonth() + 1]`); the adapter returns a **0-based array**. Call sites are rewritten to index directly rather than keeping the offset.
2. Month navigation — `months-dropdown.tsx` manipulates dates with `new Date(y, index, 1)` and `new Date(activeMonthDate.getFullYear() - 1, activeMonthDate.getMonth(), 1)` for the year arrows, then reads them back with `getFullYear()` / `getMonth()`. All of these become `adapter.addParts({year, month}, delta)` returning `{year, month}`, with a single `fromParts(y, m, 1)` at the boundary to produce the `Date` the store still holds. The store keeps a Gregorian `Date` as its source of truth and only the label and the ±1/±12 steps are adapter-driven.
3. Range titles in the same file (`"Jun 2025 - Jul 2025"`) become Persian via `adapter.format`.
4. "Is today" checks — `differenceInCalendarDays(d, today) === 0` becomes a comparison of `toParts(d)` against `toParts(today)`.
5. `week-header.tsx` — week labels computed from Persian month boundaries.

Store: `apps/web/store/issue/issue_calendar_view.store.ts` already regenerates the calendar when `start_of_the_week` changes; it now also reacts to `calendar_system`.

### 2.2 Gantt chart

`apps/web/components/gantt-chart/data/index.ts` hardcodes English `weekDays`, `months`, and `quarters` tables. For Persian:

- `months` ← `adapter.getMonthNames()`
- `weekDays` ← `adapter.getWeekdayNames()`
- `quarters` ← the Persian seasons (بهار / تابستان / پاییز / زمستان) instead of Q1–Q4

The layout logic in `views/week-view.ts`, `views/month-view.ts`, and `views/quarter-view.ts` currently positions columns by `Date` arithmetic. It moves to `{year, month, week}` coordinates, with the Gregorian `Date` materialized only at the point of data lookup.

### 2.3 Analytics charts

`apps/web/components/chart/utils.ts` → `getDateGroupingName`:

| Grouping | Gregorian today | Persian |
|---|---|---|
| DAY | `Jun 15` | `۱۵ ش۶` |
| WEEK | `Jun, Week 3` | `شهریور، هفته ۳` |
| MONTH | `Jun` / `Jun, 2025` | `شهریور` / `شهریور ۱۴۰۳` |
| YEAR | `2025` | `۱۴۰۳` |

The YEAR row is the most visible change: axis years shift from 2025 to 1403.

---

## 3. Phase 3 — Relative boundaries and email

### 3.1 Relative filters — client computes, server stays unchanged

`apps/api/plane/utils/date_utils.py` resolves `last_3_months` to `timedelta(days=90)` — a Gregorian approximation. A Persian user asking for "the last 3 months" means three Persian months, which is not 90 days.

**Decision: the client computes the exact range and sends Gregorian ISO dates.** The `custom` filter already exists and already accepts `start_date` / `end_date` (line 75), so **no API change and no backend change is required at all.**

- No `jdatetime` in `requirements/base.txt` for this purpose
- No `date_utils.py` change
- No second implementation of Persian calendar logic in Python
- One source of truth: `packages/calendar`

The client additionally computes the `previous` range for period-over-period comparison, which the adapter makes straightforward.

Issue-list relative filters (`This week`, `Overdue`, `Past due`) work the same way: the UI computes the Persian-aware boundaries and sends an explicit Gregorian range instead of a slug. The API contract is unchanged; only the payload changes.

### 3.2 What deliberately does not change in this phase

| Item | Reason |
|---|---|
| `apps/api/plane/utils/date_utils.py` | Logic moves to the client |
| `apps/api/plane/utils/exporters/` | Exports are artifacts for downstream tooling, not UI |
| All database filters | Gregorian, untouched |
| The API contract | Fixed |

### 3.3 In-app notifications

Already covered by phase 1. `notification-card/item.tsx` and `content.tsx` format client-side, so they pick up Persian automatically once `renderFormattedDate` and `calculateTimeAgo` are adapter-aware.

### 3.4 Email

Email bodies are generated server-side, so this is the one place Python needs calendar knowledge. `email_notification_task.py:221` currently formats activity time as `"%H:%M %p"`.

**Decision: use `user.profile.calendar_system` to format the date portion, and leave the body text in English.**

```
"۱۴۰۳/۰۶/۰۱، ۱۴:۳۰"   instead of   "Aug 22, 2024, 02:30 PM"
```

Translating email copy is a separate project; making the date match the user's calendar is the part that fixes the inconsistency between the app and the inbox.

This requires `jdatetime` in `apps/api/requirements/base.txt` — the **only** place Persian calendar logic is implemented in Python, and it is confined to a string-formatting helper.

Separately, `templates/emails/notifications/issue-updates.html` lines 69–85 print raw activity-log values (`target_date.new_value.0`) with no formatting at all. These are passed through a template filter that reads the recipient's `calendar_system` and formats the date.

### 3.5 Exports

| Export | Behaviour | Rationale |
|---|---|---|
| Backend CSV / XLSX / JSON | **Gregorian, unchanged** | These files feed Excel and downstream BI tooling. Changing their format is a breaking change for anyone consuming them programmatically, and there is no UI to be inconsistent with. |
| Frontend Analytics CSV (`components/analytics/export.ts`) | Persian | Generated in the browser, read by a human |
| PDF (`export-page-modal.tsx`, editor PDF, `apps/live` PDF exporter) | No change | None currently render a date |

This is a deliberate trade-off, not an oversight.

---

## 4. Testing

### 4.1 Backend (pytest)

| File | Coverage |
|---|---|
| `plane/tests/unit/.../test_profile_calendar_system.py` (new) | Field is exposed by `ProfileSerializer`; PATCH round-trips; invalid values are rejected by the choices |
| `plane/tests/unit/.../test_email_calendar_format.py` (new) | Persian profile produces a Persian date in the email; Gregorian profile is byte-identical to today's output |
| `test_issue_datetime_filters.py` (existing) | **Must pass unchanged** — proof of no regression |

### 4.2 Frontend

`packages/calendar` gets a vitest config modelled on `packages/blocks` (separate `unit` and `dom` projects). Note that `packages/utils` has no test infrastructure today — the new package is the right place for these tests rather than extending that.

| Test | Key assertion |
|---|---|
| `persian-adapter.test.ts` | Round-trip over 1000 random dates: `fromParts(toParts(d))` equals `d` |
| `persian-adapter.test.ts` | Boundaries: Nowruz (1 Farvardin), Esfand 29, Esfand 30 in a leap year (1403) |
| `persian-adapter.test.ts` | Progressive search converges within the iteration cap |
| `gregorian-adapter.test.ts` | Snapshot of current formatting — locks in that Gregorian output is unchanged |
| `persian-month-grid.test.tsx` | Day selection, month navigation, range selection, keyboard navigation |
| `date-select.test.tsx` (existing) | **Must pass unchanged** |
| `outside-click.test.tsx` (existing) | **Must pass unchanged** |
| `date-select.persian.test.tsx` (new) | The same scenarios as the existing test, in Persian mode |

### 4.3 Manual QA checklist (Persian mode)

- [ ] Today's date is correct across every page
- [ ] 31-day months (Farvardin through Shahrivar) render a full 6th row correctly
- [ ] Esfand 30 in leap year 1403
- [ ] Esfand 29 in a common year
- [ ] Picking a date writes the correct **Gregorian** value — verify directly in the database
- [ ] "Last 3 months" filter produces the correct Persian range
- [ ] Switching back to Gregorian restores the previous behaviour everywhere
- [ ] Analytics, Calendar, Gantt, Charts, Inbox, Notifications
- [ ] Email date matches the user's calendar

---

## 5. Phasing summary

| Phase | Contents | Independently shippable outcome |
|---|---|---|
| 1 | `packages/calendar`, both adapters, DB field, `datetime.ts`, Persian picker, locale-leak fixes, settings UI | Dates render in Persian; picker is Persian |
| 2 | Calendar layout, Gantt, chart axis labels | Calendar views are Persian |
| 3 | Relative boundaries, Persian email dates, frontend CSV | Filters, Analytics, and email are Persian |
| 4 | `fa-IR` locale across 29 namespaces, full RTL | *(separate project)* |

Each phase is a separate PR with its own tests and can be merged independently.

### Phase 4 notes (for later, not designed here)

The translate skill documents the process for adding a locale: copy `packages/i18n/src/locales/en` to `packages/i18n/src/locales/fa`, then register in both `packages/i18n/src/constants/language.ts` (`SUPPORTED_LANGUAGES`) and `packages/i18n/src/types/language.ts` (`TLanguage`). Persian needs six CLDR plural categories, which that skill already flags.

RTL is a much larger and riskier effort than the translation itself. `packages/i18n/src/core/set-language.ts` currently sets `lang` but never `dir`, and there is no RTL CSS anywhere in the repo. Phase 4 will need `documentElement.dir`, Tailwind logical properties, icon mirroring, and a per-component layout audit across the whole app.

---

## 6. Risks

| Risk | Mitigation |
|---|---|
| Persian date off by one somewhere | Round-trip property test over 1000 random dates; this class of bug is otherwise invisible until a user reports a wrong due date |
| Persian date out of `Intl` range (beyond years 1178–1633 SH) | The adapter falls back to Gregorian rather than rendering garbage; a dev-mode warning fires |
| A browser without `Intl` Persian support | `PersianCalendar` feature-detects at construction and degrades to Gregorian with a console warning |
| Regression on the 21 existing locales | The Gregorian path keeps `react-day-picker` untouched; existing tests must pass unchanged |
| Two sources of truth for calendar logic | The client-computes-boundaries decision in §3.1 is what prevents a Python implementation from ever being needed for filters |
| Gantt and calendar layout regressions | Phase 2 is a separate PR; if the layout proves intractable, phases 1 and 3 still ship value |
| Locale constants leaking English month names | §1.4 is part of phase 1's definition of done, not a follow-up — a screen showing `Jun` next to `۱۵ ش۶` is worse than not shipping |
