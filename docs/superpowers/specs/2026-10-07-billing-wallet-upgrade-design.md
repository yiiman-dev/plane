# کیف پول، خرید و ارتقای پلن، تراز مالی و قیمت‌گذاری پیامک

سند طراحی — مرجع قطعی پیاده‌سازی.
تاریخ ثبت: ۱۴۰۵/۰۷/۱۶ (۲۰۲۶-۱۰-۰۷)
برنج کاری: `preview` (merge شده از `feat/persian-calendar`)
سند مادر: `docs/billing-plans-and-feature-flags.md`

این سند ادامهٔ سند مادر است و قوانین آن را تغییر نمی‌دهد، مگر جایی که صریحاً خلاف آن نوشته شود. هر تصمیمی که با کد واقعی ناسازگار شد، اول این سند اصلاح می‌شود، بعد کد.

---

## ۱) وضعیت فعلی چیست

`apps/api/plane/billing` یک سیستم پرداخت کامل است: `Plan`، `Invoice`، `PaymentTransaction`، `Subscription`، `PaymentGateway`، `GatewayRoutingConfig`، و سه لایهٔ `FeatureFlag` / `PlanFeatureFlag` / `WorkspaceFeatureFlag`.

آنچه **وجود ندارد** و این سند می‌سازد:

- **دفتر کل پول.** هیچ مدل تراکنش مالی عمومی وجود ندارد. `PaymentTransaction` فقط پرداخت درگاه را ثبت می‌کند و ستون موجودی ندارد چون اصلاً موجودی‌ای وجود ندارد.
- **کیف پول.** جست‌وجوی `wallet|Wallet|credit_balance|debit` در `apps/api` صفر نتیجه دارد.
- **قیمت پیامک.** `KavenegarProvider.get_account_info()` در `apps/api/plane/utils/notifications/kavenegar.py:63` موجود است و `remaining_credit` برمی‌گرداند، ولی **هیچ‌جا صدا زده نمی‌شود** و از هیچ endpointی بیرون نمی‌آید.
- **صفحهٔ workspace در پنل کلان.** `apps/admin/app/routes.ts:18-21` فقط چهار مسیر دارد: `gateways`، `routing`، `plans`، `transactions`. هیچ مسیری برای workspace، feature flag یا کیف پول نیست.
- **feature flag در فرم پلن.** endpointهای ادمین برای `feature-flags` و `plans/<id>/feature-flags` وجود دارند ولی **هیچ UI و هیچ تایپ تایپ‌اسکریپتی** ندارند.
- **مابه‌التفاوت.** `Plan.calculate_subtotal()` در `apps/api/plane/billing/models.py:174` فقط `base + per_seat * extra_seats` حساب می‌کند. هیچ conceptی از اعتبار باقیمانده یا پلن فعال وجود ندارد.

آنچه **هست ولی معیوب است** و در این سند درست می‌شود:

- **`has_feature()` هرگز صدا زده نمی‌شود.** `apps/api/plane/billing/services/entitlements.py:177` در کد تولیدی صفر caller دارد. یعنی تا امروز هیچ قابلیتی واقعاً گیت نشده و `PlanFeatureFlag` صرفاً داده ذخیره می‌کند. سند مادر این را آگاهانه به تعویق انداخته بود (`docs/billing-plans-and-feature-flags.md:95`).
- **`retry_pending_verifications` در beat ثبت نشده.** `apps/api/plane/billing/services/tasks.py:33` فقط از راه `.delay()` اجرا می‌شود که در `try/except` پوشانده شده. اگر broker در دسترس نباشد، تراکنش هرگز دوباره تأیید نمی‌شود.
- **محدودیت per-seat وجود ندارد.** `PlanFeatureFlag.config` یک JSON آزاد است که هیچ‌چیز آن را نمی‌خواند.
- **`Plan.features` مفهومی جداگانه و بی‌اثر است.** یک لیست رشته‌ای که فقط روی کارت‌های checkout نمایش داده می‌شود.

---

## ۲) تصمیم‌های کلیدی

**M1 — پول یک واحد دارد و یک دفتر کل تنها منبع حقیقت است.**
هیچ مدلی ستون «موجودی» قابل‌دست‌کاری ندارد. هر جابه‌جایی پول یک سطر double-entry در `LedgerEntry` می‌سازد و موجودی از جمع سطرها محاسبه می‌شود. دلیل: اگر موجودی یک ستون باشد و گزارش از دفتر کل خوانده شود، این دو به‌مرور اختلاف می‌اندازند و تشخیص منشأ اختلاف ممکن نیست. واحد پول تومان است (`IRT`) و تبدیل ریال فقط در مرز adapter درگاه انجام می‌شود.

**M2 — کیف پول per-workspace است.**
هر workspace یک کیف پول دارد و هزینهٔ پیامک از آن کم می‌شود. شارژ هم per-workspace است. گزینهٔ «اعتبار per-user با توزیع بین workspaceها» رد شد چون لایهٔ تخصیص اضافه می‌کرد و ابهام می‌ساخت (با سه workspace، اعتبار کجا می‌رود؟) و با `Subscription.workspace` که در مهاجرت `0002` اضافه شده ناسازگار بود.

**M3 — ادمین کلان اعتبار دستی می‌دهد، به یک workspace مشخص.**
مبلغ در دفتر کل به حساب آن workspace منتقل می‌شود. مدیر workspace هرگز نمی‌تواند به خودش اعتبار بدهد؛ این مسیر فقط `InstanceAdminPermission` دارد.

**M4 — اعتبار دستی برگشت‌پذیر است، نه ویرایش‌پذیر.**
برگشت یک سطر معکوس می‌سازد، نه حذف یا ویرایش سطر قبلی. سطر اصلی در تاریخچه می‌ماند تا گزارش مالی هرگز دروغ نگوید.

**M5 — پول دیگر پرداخت‌نشده به موجودی قابل‌خرج برنمی‌گردد؛ به قفل می‌رود.**
اگر پرداخت کسر شده ولی پردازش نهایی شکست خورده، مبلغ به `wallet:hold` منتقل می‌شود نه به موجودی قابل‌مصرف. مدیر workspace آن را نمی‌بیند. ادمین کلان سه گزینه دارد: نهایی کردن برگشت، تلاش مجدد دستی، یا رد کردن قفل. بعد از ۹۰ روز قفل خودکار به برگشت نهایی تبدیل می‌شود تا پول برای همیشه گم نشود. این کار ریسک «دوپرداخت» را به ریسک «پول تا ۹۰ روز قفل است» تبدیل می‌کند.

**M6 — لایهٔ پروژکشن مشترک است، نه endpoint مشترک.**
سریالایزر و تابع ساخت کوئری در `billing/services/ledger.py` یکی است و از هر دو مسیر صدا زده می‌شود، ولی **دو view جدا با دو permission جدا** وجود دارد. «یک endpoint با پارامتر scope» رد شد: هر پارامتری که scope را تعیین کند قابل جعل است و یک `?scope=instance` کافی است کل دادهٔ سیستم را لو بدهد. امنیت در دامنهٔ کوئری اعمال می‌شود، نه در فیلتر کردنِ بعد از پاسخ. جزئیات در بخش ۸.

**M7 — متن `description` برای مدیر workspace عمومی می‌شود.**
متن آزاد برای دادهٔ داخلی نوشته می‌شود («هدیهٔ قرارداد سالانه با مشتری X») نه برای کاربر. ادمین کلان متن کامل را می‌بیند، مدیر workspace نسخهٔ عمومی‌شده.

**M8 — نوع محدودیت روی خود پرچم است، نه یک عدد سراسری.**
هر `FeatureFlag` یک `limit_type` دارد: `boolean` | `number` | `unlimited`. در فرم پلن، همان کنترل متناسب رندر می‌شود. عدد global برای همهٔ پرچم‌ها رد شد چون محدودیت «۵ نمودار» و «۱۰ پروژه» معنای یکسانی ندارند.

**M9 — مابه‌التفاوت در حالت‌های مختلف رفتار متفاوتی دارد و حالتش در فرم پلن قابل تنظیم است.**
حالت‌ها: `credit_remaining` (پیشنهادی و پیش‌فرض) و `no_extension`. تنظیم در پنل کلان است، نه per-plan.

**M10 — پنجرهٔ `n` روز روی خود پلن است، نه سراسری.**
هر پلن یک `renew_lock_days` دارد. مدیر_instance برای هر پلن تصمیم می‌گیرد.

**M11 — قیمت پیامک per-event و روی خود پلن است.**
برای هر نوع رویداد (منشن، تسک‌سابسکریپشن، عضویت بورد و…) مدیر_instance در فرم پلن قیمت به تومان وارد می‌کند.

**M12 — شارژ کیف پول از دو مسیر است: پرداخت موفق درگاه، و اعتبار دستی ادمین.**
مسیر دستی سه فیلد اجباری دارد: `description` (حداقل ۱۰ کاراکتر)، `created_by` (از `request.user`، **هرگز از body**)، و `source` که مقدارش `admin_grant` است. یک سقف اختیاری per-transaction دارد تا یک کلیک اشتباه کل تراز سیستم را خراب نکند.

---

## ۳) مدل داده

### `LedgerAccount` — حساب

هر سطر دفتر کل به دو حساب بستانه می‌رود. حساب‌ها یکتا و محدودند.

| فیلد        | نوع              | توضیح                                                                               |
| ----------- | ---------------- | ----------------------------------------------------------------------------------- |
| `code`      | CharField unique | `wallet:default`، `wallet:hold`، `gateway:zarinpal:receivable`، `revenue:plan_sale` |
| `kind`      | CharField        | `asset` \| `liability` \| `revenue` \| `gateway_settlement`                         |
| `title`     | CharField        | فارسی، برای UI ادمین                                                                |
| `workspace` | FK null          | فقط برای `kind=liability`                                                           |

حساب‌های `asset` (کیف پول قابل‌خرج) و `gateway:*:receivable` بستانهٔ بدهکار دارند؛ `liability` و `revenue` بستانهٔ بستانه.

### `LedgerEntry` — سطر دفتر کل

| فیلد              | نوع                          | توضیح                                                                                                    |
| ----------------- | ---------------------------- | -------------------------------------------------------------------------------------------------------- |
| `debit_account`   | FK `LedgerAccount`           |                                                                                                          |
| `credit_account`  | FK `LedgerAccount`           |                                                                                                          |
| `amount_toman`    | PositiveBigIntegerField      | **همیشه مثبت**؛ جهت از حساب‌ها می‌آید                                                                    |
| `source`          | CharField                    | `gateway` \| `admin_grant` \| `sms_charge` \| `plan_purchase` \| `upgrade` \| `refund` \| `release_hold` |
| `workspace`       | FK null                      | برای گزارش per-workspace                                                                                 |
| `description`     | TextField                    | برای `admin_grant` اجباری                                                                                |
| `created_by`      | FK `User` null               | از `request.user`؛ برای خودکار null                                                                      |
| `invoice`         | FK null                      |                                                                                                          |
| `transaction`     | FK `PaymentTransaction` null |                                                                                                          |
| `idempotency_key` | CharField unique             | کلید یکتایی؛ retry دوباره ثبت نمی‌کند                                                                    |
| `created_at`      | DateTimeField                |                                                                                                          |

قید: `debit_account != credit_account`.

**چرا `amount_toman` مثبت است:** اگر منفی بود، علامت در ذهن خواننده و در گزارش جابه‌جا می‌شد. جهت از نوع حساب می‌آید.

**`idempotency_key` چرا لازم است:** `process_callback` ممکن است دوبار اجرا شود (gateway پاسخ را تکرار می‌کند، یا تلاش مجدد دستی ادمین). بدون این کلید، هر فراخوانی یک سطر جدید می‌سازد و موجودی دو برابر می‌شود. کلید از ترکیب قطعی ساخته می‌شود، مثلاً `payment:{transaction.id}:paid` و `sms:{log_id}:charge`.

### `Wallet` — کیف پول

| فیلد                    | نوع        | توضیح                                      |
| ----------------------- | ---------- | ------------------------------------------ |
| `workspace`             | OneToOne   |                                            |
| `admin_grant_cap_toman` | BigInteger | سقف اختیاری هر اعتبار دستی؛ صفر = بدون سقف |

**موجودی ذخیره نمی‌شود.** از `LedgerAccount.objects.filter(code=f"wallet:default:{workspace.pk}").aggregate(Sum)` حساب می‌شود. کش می‌شود ولی نوشتن کش فقط پس از commit انجام می‌شود.

### تغییرات روی مدل‌های موجود

**`Plan`** — افزوده می‌شود:

- `renew_lock_days` PositiveIntegerField default 0
- `proration_mode` CharField default `credit_remaining` — روی خود `Plan`. M9 گفت «قابل تنظیم در ادمین» و اینجا دقیق‌ترش می‌کند: روی plan است نه روی instance، چون ادمین آن را در همان فرمی می‌بیند که قیمت را تنظیم می‌کند و planهای مختلف می‌توانند سیاست متفاوت داشته باشند
- `sms_prices` JSONField default dict — کلید = event code، مقدار = قیمت تومان

**`FeatureFlag`** — افزوده می‌شود:

- `limit_type` CharField default `boolean`، choices `boolean|number|unlimited`
- `unit_label` CharField blank — مثلاً «نمودار»، «پروژه»، «GB»؛ برای رندر `number`

**`PlanFeatureFlag`** — `config` به‌جای JSON آزاد، ساختارمند می‌شود:

```json
{ "enabled": true, "limit_value": 10 }
```

برای `limit_type=boolean` فقط `enabled` معتبر است. برای `number`، `limit_value` الزامی است.

**`Subscription`** — افزوده می‌شود:

- `prorated_credit_toman` BigInteger default 0 — اعتبار باقیمانده‌ای که در ارتقا مصرف شده
- `previous_subscription` FK self null — زنجیرهٔ ارتقا برای حسابرسی

---

## ۴) واحدها و مرزها

پنج واحد مستقل. هیچ‌کدام جدول دیگری را مستقیم نمی‌خواند مگر از API داخلی‌اش.

| واحد             | مسئولیت                                      | وابسته به                |
| ---------------- | -------------------------------------------- | ------------------------ |
| `money`          | دفتر کل double-entry، تراز، قفل تراکنش       | هیچ                      |
| `wallet`         | موجودی، شارژ، برداشت، قفل                    | `money`                  |
| `pricing`        | نرخ پیامک per-event، نرخ پلن، مابه‌التفاوت   | مدل `Plan`               |
| `subscriptions`  | چرخهٔ عمر، ارتقا، تمدید، انقضا               | `money`, `pricing`       |
| `reconciliation` | تطبیق callback درگاه با دفتر کل، صفحهٔ گزارش | `money`, `subscriptions` |

هر واحد یک ماژول service با توابع خالص تا حد ممکن دارد تا بدون DB قابل تست باشد.

---

## ۵) جریان خرید و ارتقا

### محاسبهٔ مابه‌التفاوت

```
def quote_upgrade(workspace, target_plan, seats, cycle):
    current = active_subscription(workspace)
    if current is None:
        return full_price(target_plan, seats, cycle)

    # قانون M10: پنجرهٔ قفل
    if target_plan.code == current.plan.code:
        days_left = (current.ends_at - now()).days
        if days_left <= target_plan.renew_lock_days:
            raise RenewalLocked(target_plan.renew_lock_days, days_left)

    full = full_price(target_plan, seats, cycle)
    if current.plan.proration_mode == "no_extension":
        return full, keep_existing_end_date(current)
    if target_plan.access_level <= current.plan.access_level:
        return full, keep_existing_end_date(current)   # ارتقا نیست

    remaining_days = max(0, (current.ends_at - now()).days)
    remaining_ratio = remaining_days / days_in_cycle(current.cycle)
    credit = int(current_charge_toman * remaining_ratio)
    return full - credit, now() + cycle_duration(cycle), credit
```

**قاعدهٔ صریح:** اگر `access_level` پلن مقصد بزرگ‌تر یا مساوی پلن فعلی باشد، **هیچ اعتباری کسر نمی‌شود** و هیچ تمدیدی انجام نمی‌شود. خرید در وسط دوره با پلن پایین‌تر فقط پول بیشتری می‌گیرد بدون سود، که برای کاربر عجیب است. ارتقای واقعی از `access_level` بالاتر شروع می‌شود.

**گرد کردن:** همهٔ محاسبات تومان و با `Decimal` انجام می‌شود، تبدیل به `int` فقط در انتها و با گرد کردن به نزدیک‌ترین هزار تومان تا فاکتور خوانا بماند. باقیماندهٔ گرد کردن در `prorated_credit_toman` ثبت می‌شود، نه دور ریخته.

### ساخت سفارش

`create_payment_order` فعلی (`apps/api/plane/billing/services/payment.py:128`) بسط می‌یابد:

1. `PlanQuoteEndpoint` جدید پارامتر `target` می‌گیرد تا دو quote بدهد: قیمت کامل و مبلغ قابل‌پرداخت، به‌علاوهٔ `credit_applied` و `new_ends_at`.
2. `PaymentOrderCreateEndpoint` مبلغ قابل‌پرداخت را در `Invoice.metadata` به‌شکل `{"proration": {...}}` می‌گذارد تا callback بتواند بازسازی کند.
3. `process_callback` هنگام `paid`:
   - سطر دفتر کل برای فروش پلن (`revenue:plan_sale`)
   - سطر دفتر کل برای اعتبار باقیمانده (`revenue:unrealized_credit`) در صورت proration
   - ایجاد `Subscription` جدید با `previous_subscription` اشاره به قبلی
   - بستن اشتراک قبلی

### قانون پنجرهٔ قفل

در سه نقطه اعمال می‌شود، نه یکی — چون راه‌های دور زدن وجود دارد:

- `PlanQuoteEndpoint` — قیمت را نشان نمی‌دهد، خطا می‌دهد
- `PaymentOrderCreateEndpoint` — دوباره بررسی می‌کند (قیمت ممکن است از قبل cache شده باشد)
- `process_callback` — **دوباره بررسی می‌کند**. اگر بین سفارش و پرداخت، پنجرهٔ قفل باز شده باشد، پرداخت رد و پول به قفل می‌رود، نه اینکه بی‌صدا فعال شود.

---

## ۶) جریان کیف پول و پیامک

### مسیر شارژ

```
درگاه تأیید می‌کند
  → سطر دفتر کل: debit gateway:zarinpal:receivable / credit wallet:default:<ws>
  → Wallet موجودی‌اش به‌روز می‌شود (از دفتر کل)

ادمین کلان شارژ می‌کند
  → سطر دفتر کل: debit admin_grant_pool / credit wallet:default:<ws>
  → description اجباری، created_by از session، سقف بررسی می‌شود
```

### مسیر مصرف پیامک

در `send_notification_channel_log` (`apps/api/plane/bgtasks/notification_channel_task.py:145`) **قبل** از ارسال:

1. workspace پیدا می‌شود، قیمت از `Plan.sms_prices[event]` خوانده می‌شود
2. اگر قیمت صفر یا event در `sms_prices` نبود → ارسال عادی بدون کسر
3. موجودی کیف پول بررسی می‌شود با `select_for_update` روی `LedgerAccount` تا دو ارسال هم‌زمان هر دو از یک موجودی کم نکنند
4. اگر موجودی کافی نبود → ارسال با وضعیت `skipped` و دلیل `insufficient_wallet_balance`، **پیامک ارسال نمی‌شود**
5. اگر کافی بود → سطر دفتر کل با `idempotency_key=f"sms:{log_id}:charge"` و سپس ارسال

**نکتهٔ مهم:** سطر دفتر کل **قبل** از ارسال نوشته می‌شود. اگر ارسال شکست بخورد، پول کم شده ولی پیامک نرفته. این عمدی است: برعکسش (ارسال، بعد کسر) خطر ارسال رایگان در صورت کرش بین دو عمل را دارد که بدتر است. هزینهٔ پیامک ناموفق در گزارش قابل تشخیص است چون `NotificationChannelLog.status=failed` در کنار سطر دفتر کل است.

### لاگ گزارش‌گیری

از `NotificationChannelLog` که **از قبل وجود دارد** (`apps/api/plane/db/models/notification.py:255`) استفاده می‌شود؛ مدل جدیدی لازم نیست. گزارش ادمین این سه جدول را کنار هم نشان می‌دهد: `LedgerEntry` (پول) + `NotificationChannelLog` (تحویل) + `Plan.sms_prices` (نرخ در لحظهٔ ارسال). نرخ باید **در لحظهٔ ارسال snapshot شود** وگرنه تغییر بعدی قیمت، گزارش گذشته را تحریف می‌کند.

---

## ۷) جریان شکست پرداخت (M5)

```
تلاش ۱..N-1 شکست  → retry_pending_verifications (اکنون در beat ثبت می‌شود)
تلاش N شکست و وضعیت مبهم (pending/processing)
  → پول به wallet:hold منتقل می‌شود
  → مدیر workspace: موجودی را نمی‌بیند
  → ادمین کلان در /billing/transactions/queued/ می‌بیند
      - نهایی کردن برگشت   → wallet:hold → wallet:default
      - تلاش مجدد دستی     → پاک کردن قفل، اجازهٔ تأیید دوباره
      - رد کردن قفل         → هیچ تغییری (پول ثابت می‌ماند، پرداخت واقعاً موفق بوده)
تلاش N شکست و وضعیت صریح failed از gateway
  → برگشت مستقیم به wallet:default (بدون قفل)
بعد از ۹۰ روز قفل باز
  → خودکار به wallet:default
```

`retry_pending_verifications` به `beat_schedule` در `apps/api/plane/celery.py:44` اضافه می‌شود. بدون این، وضعیت «پول کسر شده ولی پلن فعال نشده» خودش را تکرار می‌کند و گزارش فقط نشانه‌گذاری می‌کند. N از تنظیمات instance خوانده می‌شود، پیش‌فرض ۵ که با `MAX_VERIFY_ATTEMPTS` فعلی در `tasks.py:21` هم‌خوان است.

---

## ۸) API

### ۸.۱ امنیت گزارش مالی — قاعدهٔ اجباری

گزارش دفتر کل دادهٔ حساس است و **دو نشت مستقل** باید هم‌زمان بسته شود: نشت از راه scope، و نشت از راه پروژکشن فیلد.

**قاعدهٔ اول — دامنه در کوئری اعمال می‌شود، نه در فیلتر.**
هر view کوئری خود را با scope‌اش می‌سازد و آن را به تابع مشترک می‌دهد. تابع مشترک هیچ‌وقت پارامتر scope نمی‌گیرد و هیچ‌وقت به `created_by` یا `invoice` فیلتر نمی‌کند مگر آن‌که خودش قفل scope داشته باشد. اگر scope از پارامتر بیاید، یک `?scope=instance` یا `?workspace=all` کافی است.

**قاعدهٔ دوم — `slug` هرگز از بدنه یا کوئری خوانده نمی‌شود.**
در مسیر مدیر workspace، `slug` فقط از `kwargs` می‌آید و همان `kwargs` است که `permission.workspace_slug` را می‌سازد، پس object دریافتی و object مجاز یکی هستند. اگر view هم‌زمان یک `workspace`/`slug` اضافه در query بپذیرد و از آن استفاده کند، بررسی مجوز روی یک object انجام و خواندن از object دیگر می‌شود.

**قاعدهٔ سوم — permission صریح و محدود به نقش مدیر.**
`WorkSpaceAdminPermission` موجود **استفاده نمی‌شود**. دلیل در `apps/api/plane/app/permissions/workspace.py:61`: با `role__in=[Admin, Member]` یعنی `role__in=[20, 15]` نوشته شده، یعنی **هر عضو عادی** را عبور می‌دهد. برای گزارش مالی یک permission تازه لازم است:

```python
# apps/api/plane/billing/api/permissions.py
class WorkspaceBillingLedgerPermission(BasePermission):
    """مالی فقط برای مدیر ورک‌اسپیس. عمداً Member را شامل نمی‌شود.

    WorkSpaceAdminPermission نقش 15 را هم عبور می‌دهد و برای دادهٔ مالی کافی نیست.
    """
    def has_permission(self, request, view):
        if request.user.is_anonymous:
            return False
        return WorkspaceMember.objects.filter(
            member=request.user,
            workspace__slug=view.workspace_slug,
            role=Admin,          # فقط ۲۰ — نه role__in
            is_active=True,
        ).exists()
```

**قاعدهٔ چهارم — پروژکشن فیلد، جدا از کوئری.**
کاربر workspace هرگز این فیلدها را نمی‌بیند، چون سریالایزر عمومی و سریالایزر مدیر workspace دو کلاس مجزا هستند که فقط تابع ساخت کوئری را share می‌کنند:

| فیلد                                                | ادمین کلان | مدیر workspace                     |
| --------------------------------------------------- | ---------- | ---------------------------------- |
| `amount_toman`, `created_at`, `source`, `workspace` | ✅         | ✅                                 |
| `description`                                       | کامل       | **عمومی‌شده طبق M7**               |
| `created_by` (نام ادمین کلان)                       | ✅         | ❌ هویت کارکنان داخلی را لو می‌دهد |
| `invoice`, `transaction`                            | ✅         | ❌ قابل حدس uuid سایر مشتریان      |
| `debit_account`, `credit_account`                   | ✅         | ❌ ساختار مالی کل سیستم            |

**قاعدهٔ پنجم — فیلترها هم scope دارند.**
`source` و بازهٔ تاریخ برای هر دو مسیر مجاز است، ولی هر دو **قبل** از فیلتر شدن به دامنهٔ مجاز قفل می‌شوند. یعنی `source=admin_grant` برای مدیر workspace مجاز است فقط چون از قبل به دفتر کل همان workspace محدود شده، نه چون فیلتر اختیاری است.

**قاعدهٔ ششم — تست نشت اجباری است.**
برای هر endpoint مالی این پنج تست نوشته می‌شود و نبودشان یعنی فاز ناقص است:

1. عضو با نقش ۱۵ → `403`
2. عضو نقش ۲۰ از workspace دیگر → `403`
3. `?scope=instance` یا `?workspace=all` → یا `403` یا نادیده گرفته‌شده، **هرگز** دادهٔ کل سیستم
4. `?slug=<workspace دیگر>` → `403`
5. در پاسخ مدیر workspace، `created_by` و `invoice` وجود ندارند

**قاعدهٔ هفتم — کش فقط به‌ازای کلید scope‌دار.**
نتیجهٔ کوئری دفتر کل با کلیدی که شامل `workspace.pk` و `scope` است کش می‌شود. کلید بدون scope، نشت موجودی یک workspace را به workspace دیگر تبدیل می‌کند.

### ۸.۲ ادمین کلان — همه `InstanceAdminPermission`

| متد       | مسیر                                                   | کار                                                          |
| --------- | ------------------------------------------------------ | ------------------------------------------------------------ |
| GET       | `/api/billing/admin/workspaces/`                       | فهرست workspaceها با پلن، صندلی، موجودی کیف پول              |
| GET       | `/api/billing/admin/workspaces/<slug>/`                | جزئیات کامل: پلن، اشتراک، صندلی، اعضا، کیف پول، آخرین تراکنش |
| POST      | `/api/billing/admin/workspaces/<slug>/wallet/grant/`   | اعتبار دستی — `amount_toman`, `description` (اجباری)         |
| POST      | `/api/billing/admin/workspaces/<slug>/wallet/revoke/`  | برگشت اعتبار دستی با ذکر دلیل                                |
| GET       | `/api/billing/admin/wallets/`                          | جدول همهٔ کیف پول‌ها با فیلتر و صفحه‌بندی                    |
| GET       | `/api/billing/admin/wallets/<workspace_slug>/ledger/`  | دفتر کل آن workspace با فیلتر `source`                       |
| GET       | `/api/billing/admin/transactions/queued/`              | صف پرداخت‌های مبهم با سن، تلاش، دلیل                         |
| POST      | `/api/billing/admin/transactions/<uuid>/retry/`        | تلاش مجدد دستی                                               |
| POST      | `/api/billing/admin/transactions/<uuid>/release-hold/` | نهایی کردن برگشت قفل                                         |
| POST      | `/api/billing/admin/transactions/<uuid>/reject-hold/`  | رد قفل                                                       |
| GET       | `/api/billing/admin/reconciliation/`                   | تطبیق درگاه: آنچه درگاه گزارش کرده با دفتر کل ما             |
| GET       | `/api/billing/admin/sms-report/`                       | گزارش پیامک: حجم، هزینه، نرخ، workspaceهای پرمصرف            |
| GET       | `/api/billing/admin/feature-flags/`                    | فهرست پرچم‌ها با `granted_plan_count`                        |
| GET/POST  | `/api/billing/admin/plans/<uuid>/feature-flags/`       | grant پرچم با `limit_value`                                  |
| GET/PATCH | `/api/billing/admin/renewal-notifications/`            | زمان‌بندی اعلان تمدید                                        |

### ۸.۳ مدیر workspace — فقط `WorkspaceBillingLedgerPermission` (نقش ۲۰)

| متد | مسیر                                             | کار                                             |
| --- | ------------------------------------------------ | ----------------------------------------------- |
| GET | `/api/billing/workspaces/<slug>/billing/ledger/` | دفتر کل همان workspace — `slug` فقط از `kwargs` |
| GET | `/api/billing/workspaces/<slug>/billing/wallet/` | موجودی و ۱۰ تراکنش آخر                          |

هر دو از `billing/services/ledger.py` استفاده می‌کنند ولی سریالایزر `WorkspaceLedgerEntrySerializer` دارند که `created_by`، `invoice`، `transaction` و نام حساب‌ها را حذف می‌کند و `description` را عمومی می‌کند. هیچ پارامتر scope یا slug در query پذیرفته نمی‌شود.

### ۸.۴ کاربر عادی

| متد | مسیر                               | کار                                                                                       |
| --- | ---------------------------------- | ----------------------------------------------------------------------------------------- |
| GET | `/api/billing/plans/<code>/quote/` | دو quote: کامل و قابل‌پرداخت، به‌علاوهٔ `credit_applied`, `new_ends_at`, `renewal_locked` |

---

## ۹) UI

### پنل کلان (apps/admin) — مسیرهای جدید

| مسیر                              | محتوا                                                                                           |
| --------------------------------- | ----------------------------------------------------------------------------------------------- |
| `/billing/workspaces/`            | جدول workspaceها: نام، پلن، صندلی مصرف‌شده، موجودی کیف پول                                      |
| `/billing/workspaces/<slug>/`     | **صفحهٔ اصلی درخواست** — تب‌ها: پلن فعال، اشتراک و تاریخ انقضا، صندلی و اعضا، کیف پول و دفتر کل |
| `/billing/wallets/`               | همهٔ کیف پول‌ها                                                                                 |
| `/billing/transactions/queued/`   | صف پرداخت‌های مبهم                                                                              |
| `/billing/reconciliation/`        | تطبیق درگاه                                                                                     |
| `/billing/sms-report/`            | گزارش پیامک                                                                                     |
| `/billing/feature-flags/`         | کاتالوگ پرچم‌ها                                                                                 |
| `/billing/renewal-notifications/` | زمان‌بندی اعلان                                                                                 |

`BILLING_TABS` در `billing-layout.tsx:13` باید به این مسیرها گسترش یابد.

### فرم پلن — feature flags با limit type

در `apps/admin/app/(all)/(dashboard)/billing/plans/page.tsx` بخش جدیدی بعد از فیلدهای قیمت: کاتالوگ پرچم‌ها گروه‌بندی‌شده بر اساس `category`. برای هر پرچم، رندر بر اساس `limit_type`:

- `boolean` → `Switch`
- `number` → `Input type=number` با `unit_label` به‌عنوان suffix
- `unlimited` → برچسب «نامحدود» بدون کنترل

پرچم‌هایی که `is_active=False` دارند خاکستری و غیرقابل انتخاب‌اند. هشدار دائمی بالای بخش: «تغییر پرچم‌ها روی اشتراک‌های فعال بلافاصله اعمال می‌شود.»

### وب اپ

- **checkout** (`apps/web/app/(all)/billing/page.tsx`) — کارت هر پلن اگر `renewal_locked` باشد غیرفعال و دلیلش نمایش داده می‌شود؛ اگر `credit_applied > 0` به‌صورت خط جداگانه «اعتبار پلن فعلی» نشان داده می‌شود
- **تنظیمات billing ورک‌اسپیس** — بخش کیف پول با دفتر کل؛ `description` عمومی‌شده طبق M7

### تایپ‌ها و سرویس

`packages/types/src/billing/index.ts` فاقد `TFeatureFlag` و `TPlanFeatureFlag` است — این‌ها اضافه می‌شوند، به‌علاوهٔ `TWallet`، `TLedgerEntry`، `TWorkspaceBillingOverview`، `TUpchargeQuote`، `TQueuedTransaction`.

---

## ۱۰) قانون AGENTS.md

سند `AGENTS.md` باید قانونی اضافه کند که **هر قابلیت جدیدی که تولید می‌شود باید در کاتالوگ `FeatureFlag` ثبت شود**، وگرنه قابلیت از پلن‌بندی قابل کنترل نیست و بعداً نمی‌توان برایش محدودیت تعریف کرد. پیشنهاد متن (به‌صورت بخش جدید بعد از `## Code Style`):

```markdown
## Feature flags

- **Registration**: Every new user-facing capability MUST have a `FeatureFlag` row in
  `apps/api/plane/billing` before or in the same change that introduces it. A capability
  with no flag cannot be gated per plan and cannot be priced per seat later.
- **limit_type**: Each flag declares `boolean`, `number` or `unlimited`. Choose `number`
  with a `unit_label` whenever the capability has a countable limit — a single global
  limit across flags does not work, because "5 charts" and "10 projects" are not the same constraint.
- **Gating**: Gate the capability with `has_feature(workspace, code)` from
  `billing.services.entitlements`. Do not read `PlanFeatureFlag` directly, and do not
  branch on `plan.code` — that couples the code to the plan catalogue.
- **Testing**: Gating needs a test that covers the off case, otherwise the flag silently
  does nothing. `has_feature()` had no production caller until Phase 3 of the billing plan.

See `docs/superpowers/specs/2026-10-07-billing-wallet-upgrade-design.md` for the plan.
```

---

## ۱۱) فازبندی

| فاز   | محتوا                                                                                                                         | پیش‌نیاز | معیار پذیرش                                                                                                                                                                                                                     |
| ----- | ----------------------------------------------------------------------------------------------------------------------------- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **۰** | `LedgerAccount`، `LedgerEntry`، ماژول `money`، مهاجرت، تست double-entry                                                       | —        | هر ورودی دو بستانهٔ متوازن می‌سازد؛ `debit != credit` رد می‌شود؛ تکرار `idempotency_key` سطر دوم نمی‌سازد؛ تراز صفر است                                                                                                         |
| **۱** | `Wallet`، شارژ از درگاه، اعتبار دستی با سه فیلد اجباری و سقف، **permission گزارش مالی + هفت تست نشت**                         | ۰        | موجودی کیف پول برابر جمع سطرهای دفتر کل؛ `description` کوتاه رد می‌شود؛ `created_by` از body قابل جعل نیست؛ سقف کار می‌کند؛ مدیر workspace نمی‌تواند شارژ کند؛ **عضو نقش ۱۵ دفتر کل را نمی‌بیند**                               |
| **۲** | صفحهٔ جزئیات workspace در ادمین کلان + feature flags در فرم پلن + قانون AGENTS.md + تایپ‌ها و سرویس                           | —        | ادمین کلان پلن و کیف پول یک workspace را می‌بیند؛ grant پرچم با `limit_value` ذخیره می‌شود؛ فرم برای `number` ورودی عددی می‌رندد                                                                                                |
| **۳** | مابه‌التفاوت، پنجرهٔ قفل، per-feature limit types، **گیت کردن واقعی با `has_feature`**، تلاش مجدد در beat، صف پرداخت‌های مبهم | ۰، ۲     | ارتقا وسط دوره مبلغ درست و `ends_at` درست؛ پنجرهٔ قفل در هر سه نقطه اعمال می‌شود؛ خرید پلن پایین‌تر اعتبار کسر نمی‌کند؛ قابلیت گیت‌شده در حالت off واقعاً کار نمی‌کند؛ `retry_pending_verifications` بدون broker هم اجرا می‌شود |
| **۴** | قیمت per-event پیامک، snapshot نرخ، کسر از کیف پول، گزارش ادمین                                                               | ۱، ۲     | ارسال پیامک موجودی را کم می‌کند؛ موجودی ناکافی ارسال را skip می‌کند؛ دو ارسال هم‌زمان موجودی را دوبار کم نمی‌کنند؛ گزارش هزینه با دفتر کل می‌خواند                                                                              |
| **۵** | اعلان زمان‌بندی‌شدهٔ تمدید                                                                                                    | ۳        | مدیر در روزهای تنظیم‌شده اعلان می‌گیرد؛ روزهای گذشتهٔ آن دوره اعلان نمی‌شود؛ اعلان یک‌بار در هر بازه ارسال می‌شود                                                                                                               |

فاز ۳ پرهزینه‌ترین فاز است چون هم مابه‌التفاوت دارد، هم پنجرهٔ قفل، هم گیت کردن واقعی، هم تلاش مجدد.

---

## ۱۲) خارج از محدوده

- **پرداخت خودکار و تمدید خودکار.** ستون `Subscription.auto_renew` وجود دارد ولی پر نمی‌شود. درگاه‌های ایرانی subscription recurring ندارند؛ تمدید دستی است.
- **تبدیل ارز.** تومان واحد است. نرخ دلار برای گزارش مدیریتی لازم است اگر خواستی، ولی در دفتر کل ثبت نمی‌شود.
- **مالیات و تخفیف.** `Invoice.discount_toman` صفر است. اگر کمپین تخفیف لازم شد، به‌صورت سطر `discount` در دفتر کل اضافه می‌شود، نه دستکاری `total_toman`.
- **چند ارزی.** `Plan.currency` وجود دارد ولی فقط `IRT` پشتیبانی می‌شود.
- **پاک کردن کد مرده.** `apps/web/components/workspace/billing/root.tsx` و `comparison/*` و `packages/constants/src/payment.ts` کد مردهٔ upstream هستند. در فاز ۲ پاک می‌شوند چون همان فایل‌ها را لمس می‌کنیم.

---

## ۱۳) ریسک‌ها

| ریسک                                             | اثر                        | کاهش                                                                                                  |
| ------------------------------------------------ | -------------------------- | ----------------------------------------------------------------------------------------------------- |
| دو نوشتن هم‌زمان موجودی را کم کنند               | موجودی منفی                | `select_for_update` روی `LedgerAccount`؛ تست هم‌زمانی                                                 |
| callback تکراری                                  | موجودی دوبرابر             | `idempotency_key` یکتا                                                                                |
| تغییر بعدی `sms_prices` گزارش گذشته را تحریف کند | گزارش مالی غلط             | snapshot نرخ در لحظهٔ ارسال                                                                           |
| پول در قفل گم شود                                | از دست رفتن درآمد          | آزادسازی خودکار بعد از ۹۰ روز                                                                         |
| پرچم‌ها بی‌اثر بمانند                            | بی‌فایده بودن فاز ۲        | گیت کردن واقعی در فاز ۳ با تست حالت off                                                               |
| تلاش مجدد از beat اجرا نشود                      | پرداخت معلق                | ثبت در `beat_schedule` در فاز ۳                                                                       |
| پلن حذف/غیرفعال شود ولی اشتراک فعال دارد         | گزارش بی‌معنی              | soft-delete موجود در `admin_views.py:169` حفظ می‌شود؛ `PlanFeatureFlag` سطرها باقی می‌مانند           |
| **نشت دادهٔ مالی به اعضای عادی**                 | افشای گردش مالی کل شرکت    | `WorkSpaceAdminPermission` نقش ۱۵ را عبور می‌دهد؛ permission تازه با `role=20`. قاعدهٔ ۱ تا ۷ بخش ۸.۱ |
| **جعل scope با پارامتر query**                   | افشای کل سیستم             | scope فقط از مسیر، هرگز از query. تست اجباری شمارهٔ ۳                                                 |
| **کش بدون کلید scope**                           | نشت موجودی بین workspaceها | کلید کش شامل `workspace.pk` و `scope`                                                                 |

---

## ۱۴) معیار پذیرش کلی

- [ ] موجودی هر کیف پول از جمع سطرهای دفتر کل قابل بازتولید است
- [ ] هیچ تغییر موجودی بدون سطر دفتر کل ممکن نیست
- [ ] `idempotency_key` تکراری سطر دوم نمی‌سازد
- [ ] ارتقای پلن وسط دوره مبلغ درست و تاریخ انقضای درست تولید می‌کند
- [ ] پنجرهٔ قفل در هر سه نقطه (quote، order، callback) اعمال می‌شود
- [ ] پول کسرشدهٔ پرداخت‌ناموفق هرگز بی‌صدا گم نمی‌شود
- [ ] اعتبار دستی سه فیلد اجباری دارد و `created_by` جعل‌ناپذیر است
- [ ] قابلیت گیت‌شده در حالت off واقعاً کار نمی‌کند، با تست
- [ ] هر قابلیت جدید طبق قانون AGENTS.md پرچم دارد
- [ ] گزارش پیامک با دفتر کل می‌خواند و نرخ را snapshot دارد
- [ ] **هفت تست نشت بخش ۸.۱ پاس می‌شود، از جمله ۴۰۳ برای عضو نقش ۱۵**
- [ ] `slug` و `scope` از query پذیرفته نمی‌شود
- [ ] در پاسخ مدیر workspace فیلد `created_by` وجود ندارد
