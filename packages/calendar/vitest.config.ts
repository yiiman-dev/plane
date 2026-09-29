/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    coverage: {
      provider: "v8",
      include: ["src/**/*.{ts,tsx}"],
      exclude: ["src/**/*.stories.{ts,tsx}", "src/**/index.ts", "src/**/*types*.{ts,tsx}"],
    },
    projects: [
      {
        extends: true,
        test: {
          name: "unit",
          // Tests live in the sibling `tests/` directory, not colocated in `src/` (unlike
          // packages/blocks). Both globs are required: without the `tests/` one, every test
          // file is silently never collected and the suite passes green having run nothing.
          include: ["tests/**/*.test.ts", "src/**/*.test.ts"],
          environment: "node",
        },
      },
      {
        // Component tests need a DOM but not a real browser, so `pnpm test` stays runnable
        // without browsers. Unlike packages/blocks there is no virtualizer here, so no layout
        // stubs are needed.
        extends: true,
        test: {
          name: "dom",
          // See the `unit` project above: same `tests/`-first layout.
          include: ["tests/**/*.test.tsx", "src/**/*.test.tsx"],
          environment: "jsdom",
          setupFiles: ["./vitest.setup.dom.ts"],
        },
      },
    ],
  },
});
