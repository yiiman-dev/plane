/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useCallback, useMemo, useState } from "react";
import useSWR from "swr";
import { BILLING_INVOICES, BILLING_TRANSACTIONS, BillingService } from "@plane/services";
import type {
  TBillingCycle,
  TInvoice,
  TInvoiceStatus,
  TPaymentGatewayCode,
  TPaymentTransaction,
  TPaymentTransactionStatus,
} from "@plane/types";
import { Badge } from "@makeplane/propel/components/badge";
import { Button } from "@makeplane/propel/components/button";
import { Input } from "@makeplane/propel/components/input";
import { Pagination } from "@makeplane/propel/components/pagination";
import { Select, SelectContent, SelectItem, SelectList, SelectTrigger } from "@makeplane/propel/components/select";

import { BillingEmptyState, BillingNav, BillingRTLFrame } from "../components/billing-layout";
import { useDebouncedValue } from "../hooks";
import {
  BILLING_CYCLE_LABELS,
  BILLING_PAGE_SIZE_OPTIONS,
  GATEWAY_LABELS,
  INVOICE_STATUS_LABELS,
  INVOICE_STATUS_VARIANTS,
  PAGINATION_LABELS,
  SUPPORTED_GATEWAY_CODES,
  TRANSACTION_STATUS_LABELS,
  TRANSACTION_STATUS_VARIANTS,
} from "../constants";
import { Download } from "lucide-react";
import {
  DEFAULT_BILLING_PER_PAGE,
  downloadCsv,
  formatDateTime,
  formatNumber,
  formatToman,
  getErrorMessage,
  makeBillingCursor,
  pageToCursor,
  type TCsvColumn,
} from "../utils";

type TTab = "invoices" | "transactions";

/** Keys the gateway echoes back that carry a machine readable code or state. */
const GATEWAY_CODE_KEYS = [
  "authority",
  "code",
  "error",
  "error_code",
  "message",
  "paymentCode",
  "payment_code",
  "refId",
  "result",
  "state",
  "status",
  "trackId",
];

/**
 * Walks a gateway payload and collects the code like fields it carries. The adapter normalises
 * these into the unified status, so the raw values are what makes a failure diagnosable.
 */
const collectGatewayCodes = (payload: unknown, prefix = ""): string[] => {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return [];
  return Object.entries(payload as Record<string, unknown>).flatMap(([key, value]) => {
    if (value && typeof value === "object") return collectGatewayCodes(value, `${prefix}${key}.`);
    const matches = GATEWAY_CODE_KEYS.some((candidate) => candidate.toLowerCase() === key.toLowerCase());
    if (!matches || value === null || value === undefined || value === "") return [];
    return [`${prefix}${key}: ${String(value)}`];
  });
};

function JsonBlock({ label, payload }: { label: string; payload: Record<string, unknown> | undefined }) {
  if (!payload || !Object.keys(payload).length) return null;
  return (
    <div className="flex flex-col gap-1">
      <span className="text-11 text-tertiary">{label}</span>
      <pre
        className="rounded-custom max-h-48 overflow-auto bg-layer-2 p-2 text-11 text-secondary"
        dir="ltr"
        data-testid={`payload-${label}`}
      >
        {JSON.stringify(payload, null, 2)}
      </pre>
    </div>
  );
}

function TransactionDetails({ transaction }: { transaction: TPaymentTransaction }) {
  const codes = useMemo(
    () =>
      Array.from(
        new Set([
          ...collectGatewayCodes(transaction.meta),
          ...collectGatewayCodes(transaction.verify_payload),
          ...collectGatewayCodes(transaction.callback_payload),
        ])
      ),
    [transaction.callback_payload, transaction.meta, transaction.verify_payload]
  );

  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-2 gap-2 text-12 text-secondary md:grid-cols-3">
        <span>درگاه: {GATEWAY_LABELS[transaction.gateway_code] ?? transaction.gateway_code}</span>
        <span>شناسه تراکش: {transaction.gateway_token || "—"}</span>
        <span>شناسه مرجع درگاه: {transaction.gateway_ref_id || "—"}</span>
        <span>مبلغ: {formatToman(transaction.amount_toman)}</span>
        <span>مبلغ درگاه: {formatToman(transaction.gateway_amount)}</span>
        <span>کارمزد: {formatToman(transaction.gateway_fee)}</span>
        <span>فاکتور: {transaction.invoice_number || "—"}</span>
        <span>پرداخت‌کننده: {transaction.user_detail?.display_name || "—"}</span>
        <span>ایمیل پرداخت‌کننده: {transaction.user_detail?.email || "—"}</span>
        <span>تعداد تلاش: {formatNumber(transaction.attempts)}</span>
        <span>ایجاد: {formatDateTime(transaction.created_at)}</span>
        <span>تایید: {formatDateTime(transaction.verified_at)}</span>
        <span>پرداخت: {formatDateTime(transaction.paid_at)}</span>
      </div>

      {transaction.failure_reason && (
        <p className="text-12 text-danger-primary">علت ناموفقی: {transaction.failure_reason}</p>
      )}

      <div className="flex flex-col gap-1">
        <span className="text-11 text-tertiary">کدهای خطای برگشتی از درگاه</span>
        {codes.length ? (
          <div className="flex flex-wrap gap-1">
            {codes.map((code) => (
              <Badge key={code} size="xs" variant="neutral" label={code} />
            ))}
          </div>
        ) : (
          <span className="text-12 text-tertiary">کد خطایی ثبت نشده است.</span>
        )}
      </div>

      <JsonBlock label="داده‌های کال‌بک" payload={transaction.callback_payload} />
      <JsonBlock label="پاسخ وریفای" payload={transaction.verify_payload} />
      <JsonBlock label="متای تراکنش" payload={transaction.meta} />
    </div>
  );
}

function InvoiceDetails({ invoiceId }: { invoiceId: string }) {
  const { data, error, isLoading } = useSWR(`billing-invoice-detail-${invoiceId}`, () =>
    BillingService.invoice(invoiceId)
  );

  if (isLoading) return <BillingEmptyState message="در حال بارگذاری جزئیات فاکتور…" />;
  if (error || !data)
    return <BillingEmptyState message={getErrorMessage(error, "بارگذاری جزئیات فاکتور ناموفق بود.")} />;

  const transactions = data.transactions ?? [];

  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-2 gap-2 text-12 text-secondary md:grid-cols-3">
        <span>شماره فاکتور: {data.number}</span>
        <span>پلن: {data.plan_code || data.plan}</span>
        <span>دوره: {BILLING_CYCLE_LABELS[data.cycle]}</span>
        <span>تعداد صندلی: {formatNumber(data.seats)}</span>
        <span>جمع جزء: {formatToman(data.subtotal_toman)}</span>
        <span>تخفیف: {formatToman(data.discount_toman)}</span>
        <span>مبلغ نهایی: {formatToman(data.total_toman)}</span>
        <span>صدور: {formatDateTime(data.issued_at)}</span>
        <span>سررسید: {formatDateTime(data.due_at)}</span>
      </div>

      {data.notes && <p className="text-12 text-tertiary">توضیحات: {data.notes}</p>}

      <div className="flex flex-col gap-2">
        <span className="text-11 text-tertiary">تراکنش‌های این فاکتور</span>
        {transactions.length === 0 ? (
          <span className="text-12 text-tertiary">تراکنشی برای این فاکتور ثبت نشده است.</span>
        ) : (
          transactions.map((transaction) => (
            <div key={transaction.id} className="rounded-custom flex flex-col gap-2 border border-subtle p-3">
              <div className="flex flex-wrap items-center gap-2">
                <Badge
                  size="xs"
                  variant={TRANSACTION_STATUS_VARIANTS[transaction.status]}
                  label={TRANSACTION_STATUS_LABELS[transaction.status]}
                />
                <span className="text-12 text-secondary">
                  {GATEWAY_LABELS[transaction.gateway_code] ?? transaction.gateway_code} •{" "}
                  {formatToman(transaction.amount_toman)}
                </span>
              </div>
              <TransactionDetails transaction={transaction} />
            </div>
          ))
        )}
      </div>

      <JsonBlock label="متای فاکتور" payload={data.metadata} />
    </div>
  );
}

export default function BillingTransactionsPage() {
  const [activeTab, setActiveTab] = useState<TTab>("transactions");

  /* transactions */
  const [transactionStatus, setTransactionStatus] = useState<TPaymentTransactionStatus | "all">("all");
  const [transactionGateway, setTransactionGateway] = useState<TPaymentGatewayCode | "all">("all");
  const [transactionSearch, setTransactionSearch] = useState("");
  const [transactionPage, setTransactionPage] = useState(1);
  const [transactionPerPage, setTransactionPerPage] = useState(DEFAULT_BILLING_PER_PAGE);
  const [expandedTransaction, setExpandedTransaction] = useState<string | null>(null);
  const debouncedTransactionSearch = useDebouncedValue(transactionSearch);

  /* invoices */
  const [invoiceStatuses, setInvoiceStatuses] = useState<TInvoiceStatus[]>([]);
  const [invoiceCycle, setInvoiceCycle] = useState<TBillingCycle | "all">("all");
  const [invoiceSearch, setInvoiceSearch] = useState("");
  const [invoicePage, setInvoicePage] = useState(1);
  const [invoicePerPage, setInvoicePerPage] = useState(DEFAULT_BILLING_PER_PAGE);
  const [expandedInvoice, setExpandedInvoice] = useState<string | null>(null);
  const debouncedInvoiceSearch = useDebouncedValue(invoiceSearch);

  const transactionParams = useMemo(
    () => ({
      cursor: pageToCursor(transactionPage, transactionPerPage),
      gateway_code: transactionGateway === "all" ? undefined : transactionGateway,
      per_page: transactionPerPage,
      search: debouncedTransactionSearch.trim() || undefined,
      // The transaction endpoint filters on an exact status match, so a single value is sent.
      status: transactionStatus === "all" ? undefined : transactionStatus,
    }),
    [debouncedTransactionSearch, transactionGateway, transactionPage, transactionPerPage, transactionStatus]
  );

  const invoiceParams = useMemo(
    () => ({
      cursor: pageToCursor(invoicePage, invoicePerPage),
      cycle: invoiceCycle === "all" ? undefined : invoiceCycle,
      per_page: invoicePerPage,
      search: debouncedInvoiceSearch.trim() || undefined,
      // The invoice endpoint splits this value on commas, so several statuses arrive at once.
      status: invoiceStatuses.length ? invoiceStatuses.join(",") : undefined,
    }),
    [debouncedInvoiceSearch, invoiceCycle, invoicePage, invoicePerPage, invoiceStatuses]
  );

  const {
    data: transactionData,
    error: transactionError,
    isLoading: isTransactionLoading,
  } = useSWR(BILLING_TRANSACTIONS(transactionParams), () => BillingService.transactions(transactionParams));

  const {
    data: invoiceData,
    error: invoiceError,
    isLoading: isInvoiceLoading,
  } = useSWR(BILLING_INVOICES(invoiceParams), () => BillingService.invoices(invoiceParams));

  const transactions = useMemo<TPaymentTransaction[]>(() => transactionData?.results ?? [], [transactionData]);
  const invoices = useMemo<TInvoice[]>(() => invoiceData?.results ?? [], [invoiceData]);

  const transactionPageCount = Math.max(1, transactionData?.total_pages ?? 1);
  const invoicePageCount = Math.max(1, invoiceData?.total_pages ?? 1);
  const transactionTotal = transactionData?.total_results ?? 0;
  const invoiceTotal = invoiceData?.total_results ?? 0;
  const transactionRangeStart = (transactionPage - 1) * transactionPerPage + 1;
  const transactionRangeEnd = transactionRangeStart + transactions.length - 1;
  const invoiceRangeStart = (invoicePage - 1) * invoicePerPage + 1;
  const invoiceRangeEnd = invoiceRangeStart + invoices.length - 1;

  const toggleInvoiceStatus = useCallback((status: TInvoiceStatus) => {
    setInvoicePage(1);
    setInvoiceStatuses((previous) =>
      previous.includes(status) ? previous.filter((item) => item !== status) : [...previous, status]
    );
  }, []);

  const toggleExpandedTransaction = useCallback((transactionId: string) => {
    setExpandedTransaction((previous) => (previous === transactionId ? null : transactionId));
  }, []);

  const toggleExpandedInvoice = useCallback((invoiceId: string) => {
    setExpandedInvoice((previous) => (previous === invoiceId ? null : invoiceId));
  }, []);

  const [isExporting, setIsExporting] = useState(false);

  const handleExportCsv = async () => {
    try {
      setIsExporting(true);
      const timestamp = new Date().toISOString().slice(0, 10);

      if (activeTab === "transactions") {
        let exportRows = transactions;
        if (transactionTotal > transactions.length) {
          const fullData = await BillingService.transactions({
            ...transactionParams,
            per_page: Math.min(transactionTotal, 2000),
            cursor: makeBillingCursor(Math.min(transactionTotal, 2000), 0),
          });
          if (fullData?.results) {
            exportRows = fullData.results;
          }
        }

        const columns: TCsvColumn<TPaymentTransaction>[] = [
          { label: "شناسه تراکنش", value: (t) => t.id },
          { label: "شماره فاکتور", value: (t) => t.invoice_number ?? "" },
          { label: "مبلغ (تومان)", value: (t) => t.amount_toman },
          { label: "درگاه پرداخت", value: (t) => GATEWAY_LABELS[t.gateway_code] ?? t.gateway_code },
          { label: "وضعیت", value: (t) => TRANSACTION_STATUS_LABELS[t.status] ?? t.status },
          { label: "شناسه مرجع درگاه", value: (t) => t.gateway_ref_id ?? "" },
          { label: "توکن درگاه", value: (t) => t.gateway_token ?? "" },
          { label: "نام کاربر", value: (t) => t.user_detail?.display_name ?? "" },
          { label: "ایمیل کاربر", value: (t) => t.user_detail?.email ?? "" },
          { label: "تعداد تلاش", value: (t) => t.attempts },
          { label: "علت ناموفق بودن", value: (t) => t.failure_reason ?? "" },
          { label: "تاریخ ایجاد", value: (t) => formatDateTime(t.created_at) },
          { label: "تاریخ پرداخت", value: (t) => formatDateTime(t.paid_at) },
          { label: "تاریخ تایید", value: (t) => formatDateTime(t.verified_at) },
          { label: "تاریخ (ISO)", value: (t) => t.created_at },
        ];

        downloadCsv(`billing-transactions-${timestamp}`, columns, exportRows);
      } else {
        let exportRows = invoices;
        if (invoiceTotal > invoices.length) {
          const fullData = await BillingService.invoices({
            ...invoiceParams,
            per_page: Math.min(invoiceTotal, 2000),
            cursor: makeBillingCursor(Math.min(invoiceTotal, 2000), 0),
          });
          if (fullData?.results) {
            exportRows = fullData.results;
          }
        }

        const columns: TCsvColumn<TInvoice>[] = [
          { label: "شناسه فاکتور", value: (i) => i.id },
          { label: "شماره فاکتور", value: (i) => i.number },
          { label: "کد پلن", value: (i) => i.plan_code || i.plan },
          { label: "دوره پرداخت", value: (i) => BILLING_CYCLE_LABELS[i.cycle] ?? i.cycle },
          { label: "تعداد صندلی", value: (i) => i.seats },
          { label: "مبلغ خام (تومان)", value: (i) => i.subtotal_toman },
          { label: "تخفیف (تومان)", value: (i) => i.discount_toman },
          { label: "مبلغ کل (تومان)", value: (i) => i.total_toman },
          { label: "وضعیت", value: (i) => INVOICE_STATUS_LABELS[i.status] ?? i.status },
          { label: "نام کاربر", value: (i) => i.user_detail?.display_name ?? "" },
          { label: "ایمیل کاربر", value: (i) => i.user_detail?.email ?? "" },
          { label: "تاریخ صدور", value: (i) => formatDateTime(i.issued_at || i.created_at) },
          { label: "تاریخ پرداخت", value: (i) => formatDateTime(i.paid_at) },
          { label: "تاریخ سررسید", value: (i) => formatDateTime(i.due_at) },
          { label: "یادداشت‌ها", value: (i) => i.notes ?? "" },
          { label: "تاریخ (ISO)", value: (i) => i.created_at },
        ];

        downloadCsv(`billing-invoices-${timestamp}`, columns, exportRows);
      }
    } catch {
      const timestamp = new Date().toISOString().slice(0, 10);
      if (activeTab === "transactions") {
        const columns: TCsvColumn<TPaymentTransaction>[] = [
          { label: "شناسه تراکنش", value: (t) => t.id },
          { label: "شماره فاکتور", value: (t) => t.invoice_number ?? "" },
          { label: "مبلغ (تومان)", value: (t) => t.amount_toman },
          { label: "درگاه پرداخت", value: (t) => GATEWAY_LABELS[t.gateway_code] ?? t.gateway_code },
          { label: "وضعیت", value: (t) => TRANSACTION_STATUS_LABELS[t.status] ?? t.status },
          { label: "شناسه مرجع درگاه", value: (t) => t.gateway_ref_id ?? "" },
          { label: "توکن درگاه", value: (t) => t.gateway_token ?? "" },
          { label: "نام کاربر", value: (t) => t.user_detail?.display_name ?? "" },
          { label: "ایمیل کاربر", value: (t) => t.user_detail?.email ?? "" },
          { label: "تعداد تلاش", value: (t) => t.attempts },
          { label: "علت ناموفق بودن", value: (t) => t.failure_reason ?? "" },
          { label: "تاریخ ایجاد", value: (t) => formatDateTime(t.created_at) },
          { label: "تاریخ پرداخت", value: (t) => formatDateTime(t.paid_at) },
          { label: "تاریخ تایید", value: (t) => formatDateTime(t.verified_at) },
          { label: "تاریخ (ISO)", value: (t) => t.created_at },
        ];
        downloadCsv(`billing-transactions-${timestamp}`, columns, transactions);
      } else {
        const columns: TCsvColumn<TInvoice>[] = [
          { label: "شناسه فاکتور", value: (i) => i.id },
          { label: "شماره فاکتور", value: (i) => i.number },
          { label: "کد پلن", value: (i) => i.plan_code || i.plan },
          { label: "دوره پرداخت", value: (i) => BILLING_CYCLE_LABELS[i.cycle] ?? i.cycle },
          { label: "تعداد صندلی", value: (i) => i.seats },
          { label: "مبلغ خام (تومان)", value: (i) => i.subtotal_toman },
          { label: "تخفیف (تومان)", value: (i) => i.discount_toman },
          { label: "مبلغ کل (تومان)", value: (i) => i.total_toman },
          { label: "وضعیت", value: (i) => INVOICE_STATUS_LABELS[i.status] ?? i.status },
          { label: "نام کاربر", value: (i) => i.user_detail?.display_name ?? "" },
          { label: "ایمیل کاربر", value: (i) => i.user_detail?.email ?? "" },
          { label: "تاریخ صدور", value: (i) => formatDateTime(i.issued_at || i.created_at) },
          { label: "تاریخ پرداخت", value: (i) => formatDateTime(i.paid_at) },
          { label: "تاریخ سررسید", value: (i) => formatDateTime(i.due_at) },
          { label: "یادداشت‌ها", value: (i) => i.notes ?? "" },
          { label: "تاریخ (ISO)", value: (i) => i.created_at },
        ];
        downloadCsv(`billing-invoices-${timestamp}`, columns, invoices);
      }
    } finally {
      setIsExporting(false);
    }
  };

  const hasItemsToExport = activeTab === "transactions" ? transactions.length > 0 : invoices.length > 0;

  const exportAction = (
    <Button
      variant="secondary"
      size="sm"
      stretch="auto"
      label={activeTab === "transactions" ? "خروجی CSV تراکنش‌ها" : "خروجی CSV فاکتورها"}
      icon={<Download className="h-3.5 w-3.5" />}
      disabled={!hasItemsToExport || isExporting}
      loading={isExporting}
      onClick={handleExportCsv}
    />
  );

  return (
    <BillingRTLFrame
      title="تراکنش‌ها و فاکتورها"
      description="تراکنش‌های ثبت‌شده روی درگاه‌های پرداخت و فاکتورهای صادرشده، همراه با وضعیت و کدهای برگشتی درگاه."
      actions={exportAction}
    >
      <BillingNav />

      <div className="flex items-center gap-1">
        <Button
          variant={activeTab === "transactions" ? "primary" : "secondary"}
          size="sm"
          stretch="auto"
          label="تراکنش‌ها"
          aria-pressed={activeTab === "transactions"}
          onClick={() => setActiveTab("transactions")}
        />
        <Button
          variant={activeTab === "invoices" ? "primary" : "secondary"}
          size="sm"
          stretch="auto"
          label="فاکتورها"
          aria-pressed={activeTab === "invoices"}
          onClick={() => setActiveTab("invoices")}
        />
      </div>

      {activeTab === "transactions" ? (
        <>
          <div className="flex flex-wrap items-end gap-3">
            <div className="flex min-w-56 flex-col gap-1">
              <label className="text-13 text-tertiary" htmlFor="transaction-search">
                جست‌وجو
              </label>
              <Input
                id="transaction-search"
                size="lg"
                placeholder="شماره فاکتور، شناسه تراکش یا شناسه مرجع"
                value={transactionSearch}
                onChange={(event) => {
                  setTransactionSearch(event.target.value);
                  setTransactionPage(1);
                }}
              />
            </div>

            <div className="flex min-w-48 flex-col gap-1">
              <span className="text-13 text-tertiary">وضعیت</span>
              <Select
                value={transactionStatus}
                onValueChange={(value) => {
                  if (!value) return;
                  setTransactionStatus(value as TPaymentTransactionStatus);
                  setTransactionPage(1);
                }}
              >
                <SelectTrigger size="lg" placeholder="همه وضعیت‌ها" />
                <SelectContent>
                  <SelectList>
                    <SelectItem size="lg" value="all" label="همه وضعیت‌ها" />
                    <SelectItem size="lg" value="paid" label={TRANSACTION_STATUS_LABELS.paid} />
                    <SelectItem size="lg" value="pending" label={TRANSACTION_STATUS_LABELS.pending} />
                    <SelectItem size="lg" value="redirected" label={TRANSACTION_STATUS_LABELS.redirected} />
                    <SelectItem size="lg" value="processing" label={TRANSACTION_STATUS_LABELS.processing} />
                    <SelectItem size="lg" value="failed" label={TRANSACTION_STATUS_LABELS.failed} />
                    <SelectItem size="lg" value="unavailable" label={TRANSACTION_STATUS_LABELS.unavailable} />
                    <SelectItem size="lg" value="reversed" label={TRANSACTION_STATUS_LABELS.reversed} />
                  </SelectList>
                </SelectContent>
              </Select>
            </div>

            <div className="flex min-w-48 flex-col gap-1">
              <span className="text-13 text-tertiary">درگاه</span>
              <Select
                value={transactionGateway}
                onValueChange={(value) => {
                  if (!value) return;
                  setTransactionGateway(value as TPaymentGatewayCode);
                  setTransactionPage(1);
                }}
              >
                <SelectTrigger size="lg" placeholder="همه درگاه‌ها" />
                <SelectContent>
                  <SelectList>
                    <SelectItem size="lg" value="all" label="همه درگاه‌ها" />
                    {SUPPORTED_GATEWAY_CODES.map((code) => (
                      <SelectItem key={code} size="lg" value={code} label={GATEWAY_LABELS[code]} />
                    ))}
                  </SelectList>
                </SelectContent>
              </Select>
            </div>
          </div>

          {isTransactionLoading && <BillingEmptyState message="در حال بارگذاری تراکنش‌ها…" />}
          {!isTransactionLoading && transactionError && (
            <BillingEmptyState message={getErrorMessage(transactionError, "بارگذاری تراکنش‌ها ناموفق بود.")} />
          )}
          {!isTransactionLoading && !transactionError && transactions.length === 0 && (
            <BillingEmptyState message="تراکنشی با این فیلترها یافت نشد." />
          )}

          <ul className="flex flex-col gap-2">
            {transactions.map((transaction) => {
              const isExpanded = expandedTransaction === transaction.id;
              return (
                <li key={transaction.id} className="rounded-custom flex flex-col gap-2 border border-subtle p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge
                      size="xs"
                      variant={TRANSACTION_STATUS_VARIANTS[transaction.status]}
                      label={TRANSACTION_STATUS_LABELS[transaction.status]}
                    />
                    <span className="text-13 text-primary">
                      {GATEWAY_LABELS[transaction.gateway_code] ?? transaction.gateway_code}
                    </span>
                    <span className="text-12 text-secondary">{formatToman(transaction.amount_toman)}</span>
                    {transaction.user_detail?.email && (
                      <span className="text-11 text-tertiary">پرداخت‌کننده: {transaction.user_detail.email}</span>
                    )}
                    {transaction.invoice_number && (
                      <span className="text-11 text-tertiary">فاکتور: {transaction.invoice_number}</span>
                    )}
                    <span className="text-11 text-tertiary">{formatDateTime(transaction.created_at)}</span>
                    <Button
                      variant="secondary"
                      size="sm"
                      stretch="auto"
                      label={isExpanded ? "بستن جزئیات" : "نمایش جزئیات"}
                      aria-expanded={isExpanded}
                      onClick={() => toggleExpandedTransaction(transaction.id)}
                    />
                  </div>
                  {isExpanded && <TransactionDetails transaction={transaction} />}
                </li>
              );
            })}
          </ul>

          {transactionTotal > 0 && (
            <div className="flex flex-col gap-2">
              <p className="text-body-sm-regular text-secondary">
                نمایش {formatNumber(transactionRangeStart)} تا {formatNumber(transactionRangeEnd)} از{" "}
                {formatNumber(transactionTotal)} مورد
              </p>
              <Pagination
                page={transactionPage}
                pageCount={transactionPageCount}
                onPageChange={setTransactionPage}
                labels={PAGINATION_LABELS}
                pageSize={{
                  value: transactionPerPage,
                  options: BILLING_PAGE_SIZE_OPTIONS,
                  onValueChange: (pageSize: number) => {
                    setTransactionPerPage(pageSize);
                    setTransactionPage(1);
                  },
                }}
              />
            </div>
          )}
        </>
      ) : (
        <>
          <div className="flex flex-wrap items-end gap-3">
            <div className="flex min-w-56 flex-col gap-1">
              <label className="text-13 text-tertiary" htmlFor="invoice-search">
                جست‌وجو
              </label>
              <Input
                id="invoice-search"
                size="lg"
                placeholder="شماره فاکتور یا ایمیل کاربر"
                value={invoiceSearch}
                onChange={(event) => {
                  setInvoiceSearch(event.target.value);
                  setInvoicePage(1);
                }}
              />
            </div>

            <div className="flex min-w-48 flex-col gap-1">
              <span className="text-13 text-tertiary">دوره</span>
              <Select
                value={invoiceCycle}
                onValueChange={(value) => {
                  if (!value) return;
                  setInvoiceCycle(value as TBillingCycle);
                  setInvoicePage(1);
                }}
              >
                <SelectTrigger size="lg" placeholder="همه دوره‌ها" />
                <SelectContent>
                  <SelectList>
                    <SelectItem size="lg" value="all" label="همه دوره‌ها" />
                    <SelectItem size="lg" value="monthly" label={BILLING_CYCLE_LABELS.monthly} />
                    <SelectItem size="lg" value="yearly" label={BILLING_CYCLE_LABELS.yearly} />
                  </SelectList>
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-1">
            <span className="text-13 text-tertiary">وضعیت:</span>
            {(Object.keys(INVOICE_STATUS_LABELS) as TInvoiceStatus[]).map((status) => (
              <Button
                key={status}
                variant={invoiceStatuses.includes(status) ? "primary" : "secondary"}
                size="xs"
                stretch="auto"
                label={INVOICE_STATUS_LABELS[status]}
                aria-pressed={invoiceStatuses.includes(status)}
                onClick={() => toggleInvoiceStatus(status)}
              />
            ))}
          </div>

          {isInvoiceLoading && <BillingEmptyState message="در حال بارگذاری فاکتورها…" />}
          {!isInvoiceLoading && invoiceError && (
            <BillingEmptyState message={getErrorMessage(invoiceError, "بارگذاری فاکتورها ناموفق بود.")} />
          )}
          {!isInvoiceLoading && !invoiceError && invoices.length === 0 && (
            <BillingEmptyState message="فاکتوری با این فیلترها یافت نشد." />
          )}

          <ul className="flex flex-col gap-2">
            {invoices.map((invoice) => {
              const isExpanded = expandedInvoice === invoice.id;
              return (
                <li key={invoice.id} className="rounded-custom flex flex-col gap-2 border border-subtle p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge
                      size="xs"
                      variant={INVOICE_STATUS_VARIANTS[invoice.status]}
                      label={INVOICE_STATUS_LABELS[invoice.status]}
                    />
                    <span className="text-13 text-primary">{invoice.number}</span>
                    <span className="text-12 text-secondary">{formatToman(invoice.total_toman)}</span>
                    <span className="text-11 text-tertiary">
                      {invoice.plan_code || invoice.plan} • {BILLING_CYCLE_LABELS[invoice.cycle]} •{" "}
                      {formatNumber(invoice.seats)} صندلی
                    </span>
                    <span className="text-11 text-tertiary">{invoice.user_detail?.email}</span>
                    <span className="text-11 text-tertiary">{formatDateTime(invoice.created_at)}</span>
                    <Button
                      variant="secondary"
                      size="sm"
                      stretch="auto"
                      label={isExpanded ? "بستن جزئیات" : "نمایش جزئیات"}
                      aria-expanded={isExpanded}
                      onClick={() => toggleExpandedInvoice(invoice.id)}
                    />
                  </div>
                  {isExpanded && <InvoiceDetails invoiceId={invoice.id} />}
                </li>
              );
            })}
          </ul>

          {invoiceTotal > 0 && (
            <div className="flex flex-col gap-2">
              <p className="text-body-sm-regular text-secondary">
                نمایش {formatNumber(invoiceRangeStart)} تا {formatNumber(invoiceRangeEnd)} از{" "}
                {formatNumber(invoiceTotal)} فاکتور
              </p>
              <Pagination
                page={invoicePage}
                pageCount={invoicePageCount}
                onPageChange={setInvoicePage}
                labels={PAGINATION_LABELS}
                pageSize={{
                  value: invoicePerPage,
                  options: BILLING_PAGE_SIZE_OPTIONS,
                  onValueChange: (pageSize: number) => {
                    setInvoicePerPage(pageSize);
                    setInvoicePage(1);
                  },
                }}
              />
            </div>
          )}
        </>
      )}
    </BillingRTLFrame>
  );
}
