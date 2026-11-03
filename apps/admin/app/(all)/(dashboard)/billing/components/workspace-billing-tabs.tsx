/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ReactNode } from "react";

type TWorkspaceBillingTab = "plan" | "subscription" | "seats" | "wallet";

type TWorkspaceBillingTabsProps = {
  activeTab: TWorkspaceBillingTab;
  onChange: (tab: TWorkspaceBillingTab) => void;
  children?: ReactNode;
};

const TABS: { id: TWorkspaceBillingTab; label: string }[] = [
  { id: "plan", label: "پلن فعال" },
  { id: "subscription", label: "اشتراک و انقضا" },
  { id: "seats", label: "صندلی و اعضا" },
  { id: "wallet", label: "کیف پول و دفتر کل" },
];

export function WorkspaceBillingTabs({ activeTab, onChange, children }: TWorkspaceBillingTabsProps) {
  return (
    <div className="flex flex-wrap items-center gap-1 border-b border-subtle pb-3">
      {TABS.map((tab) => (
        <button
          key={tab.id}
          type="button"
          aria-current={activeTab === tab.id ? "page" : undefined}
          onClick={() => onChange(tab.id)}
          className={
            "rounded-custom px-3 py-1.5 text-body-sm-regular transition-colors " +
            (activeTab === tab.id
              ? "bg-accent-subtle text-accent-primary"
              : "text-secondary hover:bg-layer-2 hover:text-primary")
          }
        >
          {tab.label}
        </button>
      ))}
      {children}
    </div>
  );
}
