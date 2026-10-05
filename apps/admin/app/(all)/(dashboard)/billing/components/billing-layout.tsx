/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ReactNode } from "react";
import { Link, useLocation } from "react-router";
// plane imports
import { cn } from "@plane/utils";
import { PageWrapper } from "@/components/common/page-wrapper";

const BILLING_TABS: { href: string; label: string }[] = [
  { href: "/billing/gateways/", label: "درگاه‌های پرداخت" },
  { href: "/billing/routing/", label: "انتخاب درگاه" },
  { href: "/billing/plans/", label: "پلن‌های مالی" },
  { href: "/billing/transactions/", label: "تراکنش‌ها و فاکتورها" },
];

/** Billing routes are registered with a trailing slash, so compare both sides without one. */
const normalizePath = (path: string) => path.replace(/\/+$/, "") || "/";

/**
 * Secondary navigation shared by every billing page. The parent dashboard layout already
 * renders the instance sidebar, so billing only owns its own tab strip.
 */
export function BillingNav() {
  const { pathname } = useLocation();
  const currentPath = normalizePath(pathname);

  return (
    <nav aria-label="ناوبری درگاه پرداخت" className="flex flex-wrap items-center gap-1 border-b border-subtle pb-3">
      {BILLING_TABS.map((tab) => {
        const isActive = currentPath === normalizePath(tab.href);

        return (
          <Link
            key={tab.href}
            to={tab.href}
            aria-current={isActive ? "page" : undefined}
            className={cn("rounded-custom px-3 py-1.5 text-body-sm-regular transition-colors", {
              "bg-accent-subtle text-accent-primary": isActive,
              "text-secondary hover:bg-layer-2 hover:text-primary": !isActive,
            })}
          >
            {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}

type TBillingRTLFrameProps = {
  actions?: ReactNode;
  children: ReactNode;
  description: string;
  title: string;
};

/**
 * Renders a billing page through the shared admin page wrapper so width, spacing, header box and
 * scroll area match the rest of the panel. The right to left cover stays outside the wrapper
 * because the shared wrapper never changes document direction.
 */
export function BillingRTLFrame({ actions, children, description, title }: TBillingRTLFrameProps) {
  return (
    <div dir="rtl" className="h-full w-full">
      <PageWrapper header={{ title, description, actions }}>
        <div className="flex flex-col gap-6">{children}</div>
      </PageWrapper>
    </div>
  );
}

export function BillingSection({ children, title }: { children: ReactNode; title: string }) {
  return (
    <section className="rounded-custom flex flex-col gap-3 border border-subtle p-4">
      <h2 className="text-body-sm-semibold text-primary">{title}</h2>
      {children}
    </section>
  );
}

export function BillingEmptyState({ message }: { message: string }) {
  return (
    <div className="rounded-custom flex items-center justify-center border border-dashed border-subtle px-4 py-10 text-13 text-tertiary">
      {message}
    </div>
  );
}
