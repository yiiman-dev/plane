# وب‌سرویس ثبت زمان (Time Tracking API)

این سند روش کار با وب‌سرویس‌های ثبت زمان در Plane را توضیح می‌دهد. با این وب‌سرویس‌ها می‌توان از سیستم‌های بیرونی تایمر را استارت، متوقف، لغو کرد، زمان دستی ثبت کرد، لاگ‌ها را ویرایش یا حذف کرد و لیست و گزارش زمان‌ها را گرفت.

## ۱. احراز هویت و قواعد کلی

- همه‌ی درخواست‌ها به پیشوند `/api/v1/` ارسال می‌شوند.
- احراز هویت با API Key انجام می‌شود و کلید باید در هدر `X-Api-Key` ارسال شود:

```bash
curl -H "X-Api-Key: <TOKEN>" -H "Content-Type: application/json" \
  https://<host>/api/v1/workspaces/<slug>/projects/<project_id>/issues/<issue_id>/time-logs/
```

- هر کلید به نام کاربری صاحب خودش عمل می‌کند. تایمرها و لاگ‌ها به همان کاربر تعلق دارند.
- محدودیت نرخ درخواست (rate limit) برای API Key اعمال می‌شود.
- خطاها به شکل `{"error": "..."}` برگردانده می‌شوند. اگر ویژگی ثبت زمان در پلن workspace فعال نباشد، پاسخ ۴۰۳ همراه با پیام پلن است.
- شناسه‌ها (`project_id`، `issue_id`، `pk`) باید UUID معتبر باشند.

## ۲. خلاصه‌ی endpointها

| عملیات                           | متد      | مسیر (بعد از `/api/v1/`)                                               | وضعیت موفق                                |
| -------------------------------- | -------- | ---------------------------------------------------------------------- | ----------------------------------------- |
| لیست لاگ‌های یک تسک و جمع‌ها     | `GET`    | `workspaces/{slug}/projects/{project_id}/issues/{issue_id}/time-logs/` | `200`                                     |
| ثبت زمان دستی                    | `POST`   | `workspaces/{slug}/projects/{project_id}/issues/{issue_id}/time-logs/` | `201`                                     |
| ویرایش مدت یا توضیح یک لاگ       | `PATCH`  | `…/time-logs/{pk}/`                                                    | `200`                                     |
| حذف یک لاگ                       | `DELETE` | `…/time-logs/{pk}/`                                                    | `204`                                     |
| استارت یا ادامه‌ی تایمر          | `POST`   | `…/time-logs/timer/start/`                                             | `201` (جدید) یا `200` (ادامه/در حال اجرا) |
| توقف موقت                        | `POST`   | `…/time-logs/timer/pause/`                                             | `200`                                     |
| توقف کامل و ذخیره                | `POST`   | `…/time-logs/timer/stop/`                                              | `200`                                     |
| لغو تایمر بدون ذخیره             | `POST`   | `…/time-logs/timer/cancel/`                                            | `200`                                     |
| گزارش زمان‌های پروژه             | `GET`    | `workspaces/{slug}/projects/{project_id}/time-logs/`                   | `200`                                     |
| تایمرهای فعال کاربر در workspace | `GET`    | `workspaces/{slug}/time-logs/active-timers/`                           | `200`                                     |

## ۳. چرخه‌ی تایمر

```
        start            pause             start (ادامه)
 (بدون تایمر) ──▶ running ──▶ paused ──────────▶ running
                    │           │
                    │ stop      │ stop
                    ▼           ▼
                 لاگ ذخیره‌شده  لاگ ذخیره‌شده

 running/paused ── cancel ──▶ حذف بدون ذخیره
```

- **start**: اگر روی همین تسک تایمر `paused` باشد، همان لاگ ادامه پیدا می‌کند. اگر تایمر `running` باشد، همان مقدار فعلی برگردانده می‌شود. در غیر این صورت لاگ جدید ساخته می‌شود.
- **pause**: زمان سپری‌شده از `started_at` به `duration_seconds` اضافه می‌شود و وضعیت `paused` می‌شود. اگر تایمر از قبل paused باشد، همان مقدار برگردانده می‌شود.
- **stop**: زمان باقی‌مانده‌ی اجرا اضافه می‌شود، `end_time` ثبت می‌شود و تایمر بسته می‌شود. فیلد `description` اختیاری است و در صورت ارسال جایگزین می‌شود.
- **cancel**: لاگ در حال اجرا یا paused حذف می‌شود و هیچ زمانی ذخیره نمی‌شود.

### قانون هم‌پوشانی (overlap)

اگر کاربر تایمر در حال اجرا روی تسک دیگری داشته باشد، `start` با ۴۰۰ و کد زیر پاسخ می‌دهد، مگر اینکه تنظیمات پروژه هم‌پوشانی را مجاز کرده باشد یا کاربر در لیست استثنا باشد:

```json
{
  "error": "تایمر فعال دیگری در حال اجراست و طبق تنظیمات پروژه، هم‌پوشانی تایمر مجاز نیست.",
  "code": "timer_overlap_not_allowed",
  "active_issue_id": "…",
  "active_issue_name": "…"
}
```

## ۴. دسترسی و نقش‌ها

- ثبت زمان روی یک تسک طبق `logging_permission` پروژه بررسی می‌شود:
  - `all_members`: همه‌ی اعضای پروژه.
  - `assignee_only`: فقط Assigneeهای تسک.
  - `custom_members`: Assigneeها به‌علاوه‌ی اعضای انتخاب‌شده در تنظیمات.
  - مدیر پروژه همیشه مجاز است.
- ویرایش (`PATCH`) و حذف (`DELETE`) یک لاگ فقط برای صاحب لاگ یا مدیر پروژه مجاز است. مدیر پروژه یعنی عضو فعال با نقش Admin در پروژه.
- تنظیمات پروژه (فعال بودن ثبت زمان، هم‌پوشانی و …) در این وب‌سرویس نیست و از همان مسیر `time-tracking-settings` در اپلیکیشن مدیریت می‌شود.
- اگر کاربر عضو پروژه نباشد، همه‌ی endpointها ۴۰۳ برمی‌گردانند.

## ۵. نمونه‌های درخواست

### ثبت زمان دستی

```bash
curl -X POST "$BASE/issues/$ISSUE/time-logs/" -H "X-Api-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"hours": 1, "minutes": 30, "description": "بررسی باگ", "start_time": "2026-10-20T09:00:00Z"}'
```

بدنه می‌تواند `duration_seconds` یا ترکیب `hours`/`minutes`/`seconds` داشته باشد. اگر `start_time` نفرستید، زمان فعلی استفاده می‌شود. حداقل مدت ۱ ثانیه است.

### استارت، توقف موقت، توقف کامل

```bash
curl -X POST "$BASE/issues/$ISSUE/time-logs/timer/start/" -H "X-Api-Key: $KEY"
curl -X POST "$BASE/issues/$ISSUE/time-logs/timer/pause/" -H "X-Api-Key: $KEY"
curl -X POST "$BASE/issues/$ISSUE/time-logs/timer/stop/" -H "X-Api-Key: $KEY" \
  -H "Content-Type: application/json" -d '{"description": "پیاده‌سازی endpoint"}'
```

### ویرایش و حذف یک لاگ

```bash
curl -X PATCH "$BASE/issues/$ISSUE/time-logs/$LOG_ID/" -H "X-Api-Key: $KEY" \
  -H "Content-Type: application/json" -d '{"duration_seconds": 600}'

curl -X DELETE "$BASE/issues/$ISSUE/time-logs/$LOG_ID/" -H "X-Api-Key: $KEY"
```

ویرایش فقط `duration_seconds` و `description` را تغییر می‌دهد.

### گزارش پروژه

```bash
curl "$BASE/time-logs/?start_date=2026-10-01&end_date=2026-10-31&user_id=$USER_ID&per_page=50" \
  -H "X-Api-Key: $KEY"
```

| پارامتر      | توضیح                                           |
| ------------ | ----------------------------------------------- |
| `start_date` | شروع بازه به فرمت `YYYY-MM-DD` (شامل همین روز)  |
| `end_date`   | پایان بازه به فرمت `YYYY-MM-DD` (شامل همین روز) |
| `user_id`    | فقط لاگ‌های این کاربر                           |
| `per_page`   | تعداد در هر صفحه (پیش‌فرض ۱۰۰۰، بیشینه ۱۰۰۰)    |
| `cursor`     | برای صفحه‌ی بعدی، مقدار `next_cursor` قبلی      |

تاریخ هر لاگ بر اساس `start_time` و در نبودش `created_at` تعیین می‌شود. پاسخ شامل `results` (لاگ‌ها) و `summary` است:

```json
"summary": {
  "total_duration_seconds": 5400,
  "by_user":  [{"user_id": "…", "display_name": "…", "total_duration_seconds": 5400}],
  "by_date":  [{"date": "2026-10-20", "total_duration_seconds": 5400}]
}
```

### تایمرهای فعال کاربر

```bash
curl "$BASE/workspaces/$SLUG/time-logs/active-timers/" -H "X-Api-Key: $KEY"
```

این درخواست `active_timers` (همه‌ی تایمرهای running یا paused کاربر در workspace) و `active_timer` (اولین مورد) را برمی‌گرداند. برای نمایش تایمر زنده، `elapsed_seconds` و `server_time` را استفاده کنید.

## ۶. نکات مهم برای توسعه‌دهنده

- **منبع واحد منطق:** endpointهای `/api/v1/` همان توابع endpointهای داخلی `plane/app/views/time_tracking.py` را استفاده می‌کنند. تغییر قانون ثبت زمان را فقط در همان فایل انجام دهید.
- **گزارش‌ها:** `summary` از جمع `duration_seconds` ذخیره‌شده ساخته می‌شود. زمان تایمری که هنوز در حال اجراست در جمع‌ها نمی‌آید تا بعد از توقف.
- **کدها:** مسیرها در `apps/api/plane/api/urls/time_tracking.py` و ویوها در `apps/api/plane/api/views/time_tracking.py` هستند.
- **تست:** `apps/api/plane/tests/contract/api/test_time_tracking.py`.

اجرای تست‌ها با Docker:

```bash
docker compose -f docker-compose-test.yml run --rm --build api-tests pytest plane/tests/contract/api/test_time_tracking.py -q
```

## ۷. محدودیت‌های شناخته‌شده

- `pause`، `stop` و `cancel` تایمر را فقط بر اساس تسک و کاربر پیدا می‌کنند، نه بر اساس `project_id` در مسیر. این رفتار از endpointهای داخلی به ارث رسیده است. چون تایمر فقط متعلق به همان کاربر است، خطر عملی کم است، اما اگر کاربر عضویت پروژه را از دست بدهد هنوز می‌تواند تایمر باز خود را متوقف کند.
- در این مرحله schema مربوط به OpenAPI (drf-spectacular) برای endpointهای جدید تعریف نشده است.
