/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ActionFunctionArgs } from "react-router";
import { redirect } from "react-router";

/**
 * Dev-only shim. This fork's web app posts credentials to `/api/login`, but the Django backend in
 * this repo exposes the same handler at `/auth/sign-in/`. Rather than change the app's sign-in
 * component, forward the request to the real endpoint so the browser session is established
 * against the real auth stack.
 *
 * This exists only so a local preview can sign in. It is a pass-through: no credential handling
 * happens here, and nothing is stored locally.
 */
export async function action({ request }: ActionFunctionArgs) {
  const form = await request.formData();
  const body = new URLSearchParams();
  for (const [key, value] of form.entries()) {
    if (typeof value === "string") body.append(key, value);
  }

  const apiBase = process.env.VITE_API_BASE_URL ?? "http://localhost:8010";
  const target = new URL("/auth/sign-in/", apiBase);

  const response = await fetch(target, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
      Referer: target.origin,
      Cookie: request.headers.get("Cookie") ?? "",
    },
    body: body.toString(),
    redirect: "manual",
  });

  const setCookie = response.headers.get("set-cookie");
  if (!setCookie) {
    // Surface the backend's own error rather than a silent no-op.
    return new Response(await response.text(), { status: response.status });
  }

  const headers = new Headers();
  headers.append("Set-Cookie", setCookie);
  return redirect("/", { headers });
}
