/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { cn } from "@plane/utils";

type Props = {
  isConfigured: boolean;
};

const CONFIGURED_TEXT = {
  true: "Configured",
  false: "Not configured",
} as const;

/**
 * Renders whether the provider credentials of a notification channel are set on this instance.
 * Secret values are never rendered, only the configuration state.
 */
export function ChannelConfiguredStatus(props: Props) {
  const { isConfigured } = props;

  return (
    <span
      className={cn(
        "rounded-full border border-subtle px-2 py-0.5 text-11 font-medium whitespace-nowrap",
        isConfigured ? "text-success-primary" : "text-tertiary"
      )}
      title="This only shows whether the provider credentials are set, never their value"
    >
      {isConfigured ? CONFIGURED_TEXT.true : CONFIGURED_TEXT.false}
    </span>
  );
}
