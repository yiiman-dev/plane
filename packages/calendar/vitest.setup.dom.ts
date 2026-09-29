/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

/* oxlint-disable no-extend-native */

import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

/** Defines `Element.prototype[name]` only when jsdom has left it unimplemented. */
function stubElementMethod(name: string, value: () => unknown) {
  const proto = Element.prototype as unknown as Record<string, unknown>;
  if (typeof proto[name] === "function") return;
  proto[name] = value;
}

afterEach(() => {
  cleanup();
  // scrollIntoView is unimplemented in jsdom; the grid calls it on keyboard focus moves.
  stubElementMethod("scrollIntoView", () => undefined);
});
