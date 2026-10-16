/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useState } from "react";

/**
 * Delays a rapidly changing filter value before it becomes a request.
 *
 * The billing list endpoints are server filtered, so typing into one of their
 * inputs would otherwise fire a request per keystroke. Kept in one place rather
 * than copied per page: two copies drift, and the delay is the kind of thing that
 * then differs between two screens showing the same list.
 */
export function useDebouncedValue<TValue>(value: TValue, delay = 400): TValue {
  const [debouncedValue, setDebouncedValue] = useState(value);

  useEffect(() => {
    const timeout = setTimeout(() => setDebouncedValue(value), delay);
    return () => clearTimeout(timeout);
  }, [value, delay]);

  return debouncedValue;
}
