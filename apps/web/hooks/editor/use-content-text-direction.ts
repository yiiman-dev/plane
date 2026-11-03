/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ETextDirection } from "@plane/types";
// hooks
import { useUserProfile } from "@/hooks/store/user";

/**
 * @description The per-user text direction for markdown / rich-text content.
 *
 * Read from the server-backed profile rather than local storage: the preference has to survive
 * a reload on another machine, and a cached client value would fight the server on every load.
 * The store getter already normalizes unknown values to RTL, which matches the backend default,
 * so callers can use the result directly without re-checking it.
 *
 * @returns {ETextDirection}
 */
export function useContentTextDirection(): ETextDirection {
  const { textDirection } = useUserProfile();
  return textDirection;
}
