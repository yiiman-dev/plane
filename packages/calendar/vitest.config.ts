/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

export default defineConfig({
  // `@plane/utils` is deliberately NOT a dependency here. `@plane/utils` depends on
  // `@plane/calendar`, so declaring it (even as a devDependency) closes a cycle that turbo
  // rejects outright, breaking `turbo run build` for every consumer. It is also not needed at
  // runtime: the only consumer is this test suite. Aliasing straight to the source entry point
  // resolves the import without depending on `packages/utils/dist`, so the tests also run on a
  // clean checkout with nothing prebuilt. `fileURLToPath` rather than `URL.pathname`, which
  // yields a leading-slash path on Windows that resolves to the wrong drive.
  //
  // `@plane/constants` is aliased the same way for a different reason: this package ships against
  // no dependency on it, but `tests/calendar-layout-labels.test.ts` needs `MONTHS_LIST` /
  // `DAYS_LIST` to pin the adapter's output against the tables the web layout used to read.
  // Aliasing to source keeps that assertion from requiring `packages/constants/dist` to exist.
  resolve: {
    alias: {
      "@plane/utils": fileURLToPath(new URL("../utils/src/index.ts", import.meta.url)),
      "@plane/constants": fileURLToPath(new URL("../constants/src/index.ts", import.meta.url)),
    },
  },
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
