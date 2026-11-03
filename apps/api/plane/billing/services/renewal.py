# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Renewal reminders for workspace admins (phase 5).

A reminder is due on a configured number of days before a subscription ends.
Beat runs once a day and only looks at today: a subscription whose mark fell
on an earlier day is not reminded late, and a mark that is due today is sent
once, because ``RenewalNotice`` is unique per (subscription, mark, period end).

Dates are compared in UTC, the same zone the beat schedule uses, so a reminder
never lands on a different calendar day than the one the schedule names.
"""

# Python imports
import logging
from datetime import datetime, time, timedelta, timezone as dt_timezone
from typing import List, Optional

# Django imports
from django.db import transaction as db_transaction
from django.utils import timezone

# Module imports
from plane.billing.models import (
    DEFAULT_RENEWAL_NOTICE_DAYS,
    Invoice,
    RenewalNotice,
    RenewalNoticeSchedule,
    Subscription,
    SubscriptionStatus,
)
from plane.db.models import (
    Notification,
    NotificationChannelLog,
    User,
    UserNotificationChannel,
    WorkspaceMember,
)
from plane.db.models.notification import (
    NOTIFICATION_CHANNEL_BALE,
    NOTIFICATION_CHANNEL_SMS,
    NOTIFICATION_CHANNEL_STATUS_FAILED,
    NOTIFICATION_CHANNEL_STATUS_SENT,
    NOTIFICATION_CHANNEL_STATUS_SKIPPED,
    NOTIFICATION_EVENT_BILLING_RENEWAL,
)
from plane.utils.notifications import ChannelMessage, get_provider

logger = logging.getLogger("plane.billing")

# Workspace role that receives the reminder: the admin who can renew the plan.
ADMIN_ROLE = 20

# The schedule is validated against these bounds. A year is the longest a
# reminder can sensibly be early for a plan that bills per cycle.
MIN_NOTICE_DAY = 1
MAX_NOTICE_DAY = 365


class InvalidSchedule(ValueError):
    """The requested reminder days are not usable."""


def validate_days(days) -> List[int]:
    """Return the days sorted high to low, or raise ``InvalidSchedule``.

    Duplicates and out-of-range values are rejected rather than dropped: a
    silently ignored day would look configured and never fire.
    """
    if not isinstance(days, list) or not days:
        raise InvalidSchedule("days_before must be a non-empty list of whole numbers")
    cleaned = []
    for day in days:
        # ``bool`` is a subclass of ``int``; ``true`` in the body is not a day.
        if isinstance(day, bool) or not isinstance(day, int):
            raise InvalidSchedule("days_before must contain only whole numbers")
        if not MIN_NOTICE_DAY <= day <= MAX_NOTICE_DAY:
            raise InvalidSchedule(f"each day must be between {MIN_NOTICE_DAY} and {MAX_NOTICE_DAY}")
        cleaned.append(day)
    if len(set(cleaned)) != len(cleaned):
        raise InvalidSchedule("days_before must not repeat a day")
    return sorted(cleaned, reverse=True)


def get_schedule() -> RenewalNoticeSchedule:
    """The single schedule row, created with the default days on first read."""
    schedule = RenewalNoticeSchedule.objects.order_by("created_at").first()
    if schedule is None:
        schedule = RenewalNoticeSchedule.objects.create(days_before=list(DEFAULT_RENEWAL_NOTICE_DAYS))
    return schedule


def save_schedule(days) -> RenewalNoticeSchedule:
    schedule = get_schedule()
    schedule.days_before = validate_days(days)
    schedule.save(update_fields=["days_before", "updated_at"])
    return schedule


def _start_of_day(day) -> datetime:
    return datetime.combine(day, time.min, tzinfo=dt_timezone.utc)


def _admin_user_ids(workspace) -> List:
    return list(
        WorkspaceMember.objects.filter(workspace=workspace, role=ADMIN_ROLE, is_active=True).values_list(
            "member_id", flat=True
        )
    )


def get_or_create_renewal_invoice(subscription: Subscription) -> Optional[Invoice]:
    """Find an existing renewal invoice for this period or issue a new proforma invoice."""
    workspace = subscription.workspace
    if not workspace:
        return None

    period_str = subscription.ends_at.isoformat()
    existing = (
        Invoice.objects.filter(
            metadata__renewal_subscription_id=str(subscription.pk),
            metadata__period_ends_at=period_str,
        )
        .order_by("-created_at")
        .first()
    )
    if existing:
        return existing

    from plane.billing.services import payment as payment_service

    user = subscription.user or getattr(workspace, "owner", None)
    if not user:
        admin_ids = _admin_user_ids(workspace)
        if admin_ids:
            user = User.objects.filter(id=admin_ids[0]).first()
    if not user:
        return None

    notes = f"پیش‌فاکتور تمدید دوره اشتراک پلن «{subscription.plan.name}» برای فضای کاری {workspace.name}"
    return payment_service.issue_invoice(
        user=user,
        plan=subscription.plan,
        seats=subscription.seats,
        cycle=subscription.cycle,
        workspace_slug=workspace.slug,
        notes=notes,
        extra_metadata={
            "renewal_subscription_id": str(subscription.pk),
            "period_ends_at": period_str,
        },
        due_at=subscription.ends_at,
    )


def _send_sms_reminder(
    workspace,
    user: User,
    subscription: Subscription,
    plan_name: str,
    workspace_name: str,
    days_before: int,
    invoice: Optional[Invoice],
    notif_data: dict,
) -> None:
    mobile = getattr(user, "mobile_number", None)
    if not mobile:
        return

    text = f"اشتراک پلن «{plan_name}» فضای کاری «{workspace_name}» {days_before} روز دیگر به پایان می‌رسد."
    if invoice:
        text += f"\nپیش‌فاکتور تمدید: {invoice.number} ({invoice.total_toman:,} تومان)"

    provider = get_provider(NOTIFICATION_CHANNEL_SMS)
    if not provider.is_configured():
        NotificationChannelLog.objects.create(
            workspace=workspace,
            receiver=user,
            channel=NOTIFICATION_CHANNEL_SMS,
            event=NOTIFICATION_EVENT_BILLING_RENEWAL,
            entity_name="billing_subscription",
            entity_identifier=subscription.pk,
            status=NOTIFICATION_CHANNEL_STATUS_SKIPPED,
            error_message="Kavenegar is not configured",
            data={**notif_data, "text": text},
        )
        return

    message = ChannelMessage(text=text, title=f"یادآوری تمدید {plan_name}")
    try:
        result = provider.send_to_user(user, message)
        is_sent = bool(result and result.ok)
        error_msg = "" if is_sent else (result.summary if result else "Delivery failed")
    except Exception as exc:
        is_sent = False
        error_msg = str(exc)[:255]

    NotificationChannelLog.objects.create(
        workspace=workspace,
        receiver=user,
        channel=NOTIFICATION_CHANNEL_SMS,
        event=NOTIFICATION_EVENT_BILLING_RENEWAL,
        entity_name="billing_subscription",
        entity_identifier=subscription.pk,
        status=NOTIFICATION_CHANNEL_STATUS_SENT if is_sent else NOTIFICATION_CHANNEL_STATUS_FAILED,
        sent_at=timezone.now() if is_sent else None,
        error_message=error_msg,
        data={**notif_data, "text": text},
    )


def _send_bale_reminder(
    workspace,
    user: User,
    subscription: Subscription,
    plan_name: str,
    workspace_name: str,
    days_before: int,
    invoice: Optional[Invoice],
    notif_data: dict,
) -> None:
    has_bale = UserNotificationChannel.objects.filter(
        user=user, channel=NOTIFICATION_CHANNEL_BALE, is_enabled=True
    ).exists()
    if not has_bale and not getattr(user, "bale_chat_id", None):
        return

    provider = get_provider(NOTIFICATION_CHANNEL_BALE)
    if not provider.is_configured():
        return

    text = (
        f"🔔 یادآوری سررسید اشتراک پلن «{plan_name}»\n"
        f"فضای کاری: {workspace_name}\n"
        f"مهلت باقی‌مانده: {days_before} روز\n"
    )
    if invoice:
        text += (
            f"شماره پیش‌فاکتور تمدید: {invoice.number}\n"
            f"مبلغ قابل پرداخت: {invoice.total_toman:,} تومان\n"
        )

    message = ChannelMessage(text=text, title=f"یادآوری تمدید {plan_name}")
    try:
        result = provider.send_to_user(user, message)
        is_sent = bool(result and result.ok)
        error_msg = "" if is_sent else (result.summary if result else "Delivery failed")
    except Exception as exc:
        is_sent = False
        error_msg = str(exc)[:255]

    NotificationChannelLog.objects.create(
        workspace=workspace,
        receiver=user,
        channel=NOTIFICATION_CHANNEL_BALE,
        event=NOTIFICATION_EVENT_BILLING_RENEWAL,
        entity_name="billing_subscription",
        entity_identifier=subscription.pk,
        status=NOTIFICATION_CHANNEL_STATUS_SENT if is_sent else NOTIFICATION_CHANNEL_STATUS_FAILED,
        sent_at=timezone.now() if is_sent else None,
        error_message=error_msg,
        data={**notif_data, "text": text},
    )


def _send_email_reminder(
    workspace,
    user: User,
    subscription: Subscription,
    plan_name: str,
    workspace_name: str,
    days_before: int,
    invoice: Optional[Invoice],
) -> None:
    if not getattr(user, "email", None):
        return

    try:
        from plane.license.utils.instance_value import get_email_configuration
        from django.core.mail import EmailMultiAlternatives, get_connection

        (
            EMAIL_HOST,
            EMAIL_HOST_USER,
            EMAIL_HOST_PASSWORD,
            EMAIL_PORT,
            EMAIL_USE_TLS,
            EMAIL_USE_SSL,
            EMAIL_FROM,
        ) = get_email_configuration()

        if not EMAIL_HOST:
            return

        subject = f"یادآوری سررسید اشتراک پلن «{plan_name}» - {workspace_name}"
        body = (
            f"سلام {getattr(user, 'display_name', '') or user.username}،\n\n"
            f"اشتراک پلن «{plan_name}» برای فضای کاری «{workspace_name}» تا {days_before} روز دیگر به پایان می‌رسد.\n"
        )
        if invoice:
            body += (
                f"پیش‌فاکتور تمدید با شماره {invoice.number} به مبلغ {invoice.total_toman:,} تومان صادر شده است.\n"
            )
        body += "\nجهت بررسی و تمدید اشتراک به پنل مدیریت مالی فضای کاری خود مراجعه نمایید.\n\nبا احترام،\nتیم پشتیبانی"

        connection = get_connection(
            host=EMAIL_HOST,
            port=int(EMAIL_PORT or 587),
            username=EMAIL_HOST_USER,
            password=EMAIL_HOST_PASSWORD,
            use_tls=EMAIL_USE_TLS == "1",
            use_ssl=EMAIL_USE_SSL == "1",
            timeout=5,
        )
        msg = EmailMultiAlternatives(
            subject=subject,
            body=body,
            from_email=EMAIL_FROM or "no-reply@plane.so",
            to=[user.email],
            connection=connection,
        )
        msg.send()
    except Exception as exc:
        logger.warning("billing: failed to send renewal email to %s: %s", user.email, exc)


def _dispatch_channel_notifications(
    subscription: Subscription,
    days_before: int,
    recipients: List,
    invoice: Optional[Invoice],
    notif_data: dict,
) -> None:
    if not recipients:
        return

    workspace = subscription.workspace
    workspace_name = workspace.name if workspace else "Plane"
    plan_name = subscription.plan.name

    users = list(User.objects.filter(id__in=recipients))
    for user in users:
        _send_sms_reminder(workspace, user, subscription, plan_name, workspace_name, days_before, invoice, notif_data)
        _send_bale_reminder(workspace, user, subscription, plan_name, workspace_name, days_before, invoice, notif_data)
        _send_email_reminder(workspace, user, subscription, plan_name, workspace_name, days_before, invoice)


def _notify(
    subscription: Subscription,
    days_before: int,
    recipients: List,
    invoice: Optional[Invoice] = None,
) -> None:
    plan_name = subscription.plan.name
    title = f"اشتراک پلن «{plan_name}» {days_before} روز دیگر به پایان می‌رسد"
    notif_data = {"subscription_id": str(subscription.pk), "days_before": days_before}
    if invoice:
        notif_data.update({
            "invoice_id": str(invoice.pk),
            "invoice_number": invoice.number,
            "total_toman": invoice.total_toman,
        })
    for user_id in recipients:
        Notification.objects.create(
            workspace=subscription.workspace,
            receiver_id=user_id,
            title=title,
            entity_name="billing_subscription",
            entity_identifier=subscription.pk,
            sender="billing",
            data=notif_data,
        )
    _dispatch_channel_notifications(subscription, days_before, recipients, invoice, notif_data)


def send_due_renewal_notices(today=None) -> int:
    """Send every reminder whose mark is today. Returns how many were sent.

    ``today`` exists so tests can pick the day; beat leaves it unset.
    """
    today = today or timezone.now().astimezone(dt_timezone.utc).date()
    days = sorted(set(get_schedule().days_before or []))
    if not days:
        return 0

    # A subscription ending on day D has its mark for day ``D - n`` on today
    # when ``D == today + n``. Only subscriptions ending inside the widest
    # window can have a mark today, so the query is bounded by it.
    day_start = _start_of_day(today)
    candidates = Subscription.objects.select_related("plan", "workspace").filter(
        status=SubscriptionStatus.ACTIVE,
        workspace__isnull=False,
        ends_at__gte=day_start + timedelta(days=min(days)),
        ends_at__lt=day_start + timedelta(days=max(days) + 1),
    )

    sent = 0
    for subscription in candidates:
        ends_on = subscription.ends_at.astimezone(dt_timezone.utc).date()
        for days_before in days:
            if ends_on != today + timedelta(days=days_before):
                continue
            sent += _send_one(subscription, days_before)
    return sent


def _send_one(subscription: Subscription, days_before: int) -> int:
    """Record one reminder and notify the admins, or do nothing if it already went out."""
    with db_transaction.atomic():
        # ``get_or_create`` is the race guard: two beat workers that reach this
        # line together see one row, and only the creator notifies.
        notice, created = RenewalNotice.objects.get_or_create(
            subscription=subscription,
            days_before=days_before,
            period_ends_at=subscription.ends_at,
        )
        if not created:
            return 0
        invoice = get_or_create_renewal_invoice(subscription)
        if invoice:
            notice.invoice = invoice
        recipients = _admin_user_ids(subscription.workspace)
        notice.recipients = len(recipients)
        update_fields = ["recipients", "updated_at"]
        if invoice:
            update_fields.append("invoice")
        notice.save(update_fields=update_fields)
        _notify(subscription, days_before, recipients, invoice=invoice)
    logger.info(
        "billing: renewal notice %s days before subscription %s to %s admins",
        days_before,
        subscription.pk,
        len(recipients),
    )
    return 1
