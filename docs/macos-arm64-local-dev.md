# راه‌اندازی محلی Plane روی این مک (Apple M1 Pro / arm64)

این سند تمام مشکلاتی را که برای بالا آوردن Plane روی این مک پیش آمد
جمع می‌کند و راه‌حل هر کدام را توضیح می‌دهد. همه‌ی این‌ها در
`plane-dev.sh` خودکار شده‌اند.

## دستور اصلی (همه‌چیز با یک خط)

```bash
cd /Volumes/OWC/projectsOWC/github/plane
sh plane-dev.sh
```

این دستور به‌ترتیب: پیش‌نیازها را بررسی می‌کند، ایمیج API را برای
`linux/amd64` می‌سازد (اگر موجود نباشد)، سرویس‌های docker را بالا
می‌آورد، منتظر پاسخ‌گویی API می‌ماند، و بعد dev server های وب (۳۰۰۰)
و ادمین (۳۰۰۱) را اجرا می‌کند.

| آدرس                            | سرویس                                                    |
| ------------------------------- | -------------------------------------------------------- |
| http://localhost:3000           | وب اپ (React Router)                                     |
| http://localhost:3001/god-mode/ | پنل ادمین / فرم ساخت اولین ادمین (اسلش انتهایی لازم است) |
| http://localhost:8000           | Django API                                               |
| http://localhost:9000           | S3 (rustfs)                                              |
| http://localhost:5433           | PostgreSQL (پورت ۵۴۳۲ اشغال است)                         |
| http://localhost:6380           | Redis / valkey (پورت ۶۳۷۹ را `lobe-redis` گرفته)         |

### دستورهای دیگر

```bash
sh plane-dev.sh status        # وضعیت و سلامت همه‌ی سرویس‌ها
sh plane-dev.sh doctor        # فقط بررسی پیش‌نیازها، بدون هیچ تغییری
sh plane-dev.sh down          # توقف کامل (داده‌ها در volume ها می‌ماند)
sh plane-dev.sh restart       # down + up
sh plane-dev.sh rebuild       # بیلد اجباری ایمیج amd64 و بالا آوردن
sh plane-dev.sh reset         # خطرناک: پاک کردن volume ها از نو
sh plane-dev.sh logs web      # دنبال کردن لاگ وب (admin|api|worker|beat-worker|migrator)
```

اگر ایمیج `plane-api-dev` از قبل ساخته شده باشد، `up` دیگر بیلد نمی‌کند
(بیلد amd64 روی این مک حدود ۸ دقیقه طول می‌کشد)؛ همان بار اول که به
پیام `ok ایمیج plane-api-dev موجود است` رسیدید، بعدی‌ها فقط سرویس‌ها را
بالا می‌آورند.

متغیرهای محیطی مفید:

```bash
PLANE_FORCE_BUILD=1 sh plane-dev.sh up   # حتی اگر ایمیج هست، دوباره بیلد کن
PLANE_SKIP_FRONTEND=1 sh plane-dev.sh up  # فقط بک‌اند
PLANE_SKIP_ADMIN=1 sh plane-dev.sh up      # بدون پنل ادمین
PLANE_NODE_BIN=/opt/homebrew/Cellar/node/26.0.0/bin/node sh plane-dev.sh up
```

لاگ‌ها و pid ها در `.devstack/` (در `.gitignore` اضافه شده) ذخیره می‌شوند.

## چه چیزی کجا اجرا می‌شود

| بخش                                | محل اجرا                              |
| ---------------------------------- | ------------------------------------- |
| PostgreSQL, Redis, RabbitMQ, S3    | کانتینر                               |
| API, worker, beat-worker, migrator | کانتینر (ایمیج مشترک `plane-api-dev`) |
| وب (۳۰۰۰) و ادمین (۳۰۰۱)           | dev server روی خود مک با node هوم‌برو |

## مشکلات این مک و راه‌حل‌ها

### ۱) پورت ۵۴۳۲ اشغال است

پروژه‌ی `db-designer` روی همین مک PostgreSQL را روی ۵۴۳۲ گرفته است. اپلیکیشن
از داخل شبکه‌ی docker به `plane-db:5432` وصل می‌شود، پس فقط پورت منتشرشده
جابه‌جا شده است:

```yaml
plane-db:
  ports: !override
    - "5433:5432"
```

### ۲) پورت ۳۱۰۰ اشغال است

`db-designer-web` روی ۳۱۰۰ است، پس اپ `live` قابل اجرا نیست مگر پورتش را
در `apps/live` تغییر دهید. اپ‌های `space` (۳۰۰۲) و `live` به‌صورت پیش‌فرض
اجرا نمی‌شوند.

### ۳) ایمیج MinIO از quay.io قابل دریافت نیست (401)

```
docker pull quay.io/minio/minio:RELEASE.2025-09-07T16-13-09Z
→ 401 Unauthorized
```

به همین دلیل در `docker-compose-local.nominedocker.yml` سرویس
`plane-minio` با `rustfs/rustfs` جایگزین شده (همان API سازگار با S3).
ساخت bucket را خود کانتینر API با `python manage.py create_bucket`
انجام می‌دهد، پس `mc mb` دیگر لازم نیست.

### ۴) بیلد باید روی linux/amd64 باشد ولی زیرساخت روی arm64

- سرویس‌های پایتونی (api/worker/beat/migrator) با `platform: linux/amd64`
  در override ست شده‌اند، چون زیرساخت روی این مک arm64 است و بیلد amd64
  شبیه‌سازی‌شده (Rosetta/qemu) انجام می‌شود.
- بیلد اول **۸ تا ۱۰ دقیقه** طول می‌کشد (مرحله‌ی سنگین `apk add` و
  `pip install`). بعد از آن cache است و بیلدهای بعدی چند ثانیه‌اند.
- چهار سرویس پایتونی **یک ایمیج مشترک** `plane-api-dev` می‌سازند. اگر
  همه با هم بیلد شوند، چهار بار `pip install` تکرار می‌شود.
- `docker compose build` در نسخه‌ی ۵.۳ کلید `--platform` ندارد؛ پلتفرم از
  همان `platform:` داخل فایل override خوانده می‌شود.

### ۵) `pnpm` روی PATH نیست

`pnpm dev` کار نمی‌کند چون corepack فعال نشده:

```bash
corepack enable pnpm          # اگر در PATH نبود:
/Applications/Orkas.app/Contents/Resources/runtime/node/darwin-arm64/bin/corepack enable pnpm
```

### ۶) خطای ماژول native رول‌داون (مهم‌ترین گیر)

```
Error: code signature in '.../rolldown-binding.darwin-arm64.node' not valid
for use in process: mapping process and mapped file (non-platform) have
different Team IDs
```

علت دقیق: `node` استاتیکی که داخل اپ Orkas است با **Hardened Runtime**
و TeamID (`MD479BZ2HA`) امضا شده و macOS لود هر کتابخانه‌ی native بدون
TeamID را بلاک می‌کند. binding رول‌داون فقط **adhoc** امضا شده
(`flags=0x2(adhoc)`). به همین دلیل dev server با node داخل Orkas بالا
نمی‌آید.

راه‌حل: استفاده از node هوم‌برو که TeamID ندارد:

```bash
/opt/homebrew/Cellar/node/26.0.0/bin/node node_modules/@react-router/dev/bin.cjs dev --port 3000
```

اسکریپت `plane-dev.sh` خودش این را تست می‌کند: binding رول‌داون را با
هر node موجود پیدا می‌کند و اولین node سازگار را انتخاب می‌کند. اگر هیچ‌کدام
سازگار نبودند، خطای قابل‌فهم با راه‌حل چاپ می‌کند.

بررسی دستی:

```bash
codesign -dv /Applications/Orkas.app/Contents/Resources/runtime/node/darwin-arm64/bin/node | grep -E 'flags|TeamIdentifier'
codesign -dv /opt/homebrew/Cellar/node/26.0.0/bin/node | grep -E 'flags|TeamIdentifier'
```

### ۷) compose همیشه باید با دو فایل اجرا شود

override به‌تنهایی کار نمی‌کند چون volume ها را تعریف نکرده است:

```
service "plane-minio" refers to undefined volume uploads: invalid compose project
```

دستور درست:

```bash
docker compose -f docker-compose-local.yml -f docker-compose-local.nominedocker.yml up -d
```

### ۸) دکمه‌ی Get started به ۳۰۰۱ می‌رود — باگ نیست

تا وقتی در دیتابیس `is_setup_done = false` باشد و جدول `instance_admins`
خالی باشد، `apps/web/lib/wrappers/instance-wrapper.tsx` صفحه‌ی
`InstanceNotReady` نشان می‌دهد و دکمه به `GOD_MODE_URL`
(`http://localhost:3001/god-mode/`) لینک است. یعنی باید اولین ادمین را
از پنل ادمین بسازید. برای همین **ادمین روی ۳۰۰۱ باید بالا باشد**؛
اسکریپت آن را اجرا می‌کند.

بعد از ساخت ادمین، ریشه‌ی ۳۰۰۰ مستقیم به اپلیکیشن می‌رود.

### ۹) `setup.sh` با فرم setup اشتباه گرفته می‌شود

`setup.sh` فقط کارهای زیر را می‌کند و **هیچ نام کاربری نمی‌خواهد**:

- کپی `.env.example` به `.env` برای ریشه و هر اپ
- ساختن `SECRET_KEY` برای Django
- `corepack enable pnpm` و `pnpm install`

فرم ساخت ادمین یک مرحله‌ی جداگانه و runtime است که در
http://localhost:3001/god-mode/ انجام می‌شود.

`plane-dev.sh` فقط بخش فایل‌های `.env` و `SECRET_KEY` را خودکار
می‌کند و `pnpm install` را اجرا نمی‌کند (اگر `node_modules` نبود، دستور
نصب را چاپ می‌کند و متوقف می‌شود).

### ۱۰) پنل ادمین فقط با اسلش انتهایی باز می‌شود

در این نسخه، dev server اپ ادمین روی مسیر `http://localhost:3001/god-mode`
بدون اسلش انتهایی `404` می‌دهد و فقط `http://localhost:3001/god-mode/`
پاسخ `200` می‌گیرد. ریشه‌ی `http://localhost:3001/` هم به‌صورت خودکار
به همان آدرس با اسلش ریدایرکت می‌شود. اگر دکمه‌ی `Get started` صفحه‌ی
`404` نشان داد، دستی آدرس دارای اسلش را باز کنید.

مقدار `VITE_ADMIN_BASE_PATH` در `apps/web/.env` (که از `.env.example`
ساخته می‌شود) `/god-mode` است؛ برای اینکه لینک داخل اپ هم درست باشد
کافی است مقدارش را به `/god-mode/` تغییر دهید و dev server وب را ری‌استارت
کنید. `plane-dev.sh` فایل `.env` موجود را بازنویسی نمی‌کند.

### ۱۱) پروسه‌ی قدیمی روی پورت ۳۰۰۰

dev server قبلی باعث می‌شد پورت اشغال بماند و بیلد/اجرای جدید بالا نیاید.
اسکریپت قبل از اجرا، پروسه‌های خودِ اپ را می‌کشد و اگر پروسه‌ی غریبه‌ای
پورت را گرفته باشد، خطا می‌دهد و آن را نمی‌کشد.

### ۱۲) پورت ۶۳۷۹ را پروژه‌ی دیگری گرفته (علت اصلی ۵۰۰ شدن API)

علائم: `http://localhost:8000/` پاسخ ۲۰۰ می‌دهد ولی
`/api/instances/` خطای ۵۰۰ می‌دهد و در لاگ API این است:

```
django_redis.exceptions.ConnectionInterrupted: Redis ConnectionError:
Error -2 connecting to plane-redis:6379. Name does not resolve.
```

یا `docker inspect plane-plane-redis-1` شبکه‌ای نشان نمی‌دهد
(`{{range $k,$v := .NetworkSettings.Networks}}` خالی).

علت: کانتینر `lobe-redis` از پروژه‌ی دیگری روی همین مک پورت ۶۳۷۹ را
گرفته است (`0.0.0.0:6379->6379/tcp`). کانتینر Plane نمی‌تواند پورت را
بگیرد، بالا می‌آید ولی **بدون شبکه** می‌ماند، و DNS داخل شبکه‌ی docker
برای بقیه‌ی سرویس‌ها کار نمی‌کند.

راه‌حل (اعمال‌شده): در `docker-compose-local.nominedocker.yml` پورت سمت
هاست Redis به ۶۳۸۰ منتقل شده است. اپلیکیشن همچنان `plane-redis:6379` را
روی شبکه‌ی docker صدا می‌زند؛ فقط پورت منتشرشده‌ی هاست جابه‌جا شده و
`apps/live/.env` هم توسط اسکریپت روی ۶۳۸۰ هماهنگ می‌شود.

```bash
docker ps --format '{{.Names}}\t{{.Ports}}' | grep -E ':6379->'   # دزد پورت
```

اگر روزی پروژه‌ی دیگری ۶۳۸۰ را گرفت، فقط عدد را در دو جای
`docker-compose-local.nominedocker.yml` و `plane-dev.sh` (`REDIS_PORT`)
عوض کنید.

## فایل‌های ایجادشده یا تغییرکرده

| فایل                                        | وضعیت                                                    |
| ------------------------------------------- | -------------------------------------------------------- |
| `plane-dev.sh`                              | جدید — اسکریپت اصلی راه‌اندازی                           |
| `docker-compose-local.nominedocker.yml`     | override محلی (rustfs، amd64، ایمیج مشترک، پورت‌ها)      |
| `docker-compose-local.nominedocker.yml.bak` | نسخه‌ی پشتیبان — دیگر لازم نیست                          |
| `apps/api/Dockerfile.dev.local`             | **استفاده نمی‌شود** (جایگزین‌شده با Dockerfile.dev رسمی) |
| `.devstack/`                                | وضعیت runtime (لاگ و pid) — در `.gitignore` اضافه شده    |
| `.gitignore`                                | یک خط برای `.devstack/` اضافه شد                         |
| `docs/macos-arm64-local-dev.md`             | همین سند — همه‌ی گیرها و راه‌حل‌ها                       |

## تست بک‌اند

```bash
docker compose -f docker-compose-local.yml -f docker-compose-local.nominedocker.yml \
  run --rm api-tests pytest -m unit      # طبق AGENTS.md ریپو
```
