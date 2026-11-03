/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

const getEnvVar = (key: string, fallback = ""): string => {
  const g = typeof globalThis !== "undefined" ? (globalThis as Record<string, any>) : undefined;
  if (g?.__PLANE_ENV__?.[key]) return g.__PLANE_ENV__[key];
  if (g?.process?.env?.[key]) return g.process.env[key];
  if (typeof process !== "undefined" && process?.env?.[key]) {
    return process.env[key];
  }
  return fallback;
};

export const API_BASE_URL = getEnvVar("VITE_API_BASE_URL");
export const API_BASE_PATH = getEnvVar("VITE_API_BASE_PATH");
export const API_URL = encodeURI(`${API_BASE_URL}${API_BASE_PATH}`);
// God Mode Admin App Base Url
export const ADMIN_BASE_URL = getEnvVar("VITE_ADMIN_BASE_URL");
export const ADMIN_BASE_PATH = getEnvVar("VITE_ADMIN_BASE_PATH");
export const GOD_MODE_URL = encodeURI(`${ADMIN_BASE_URL}${ADMIN_BASE_PATH}`);
// Publish App Base Url
export const SPACE_BASE_URL = getEnvVar("VITE_SPACE_BASE_URL");
export const SPACE_BASE_PATH = getEnvVar("VITE_SPACE_BASE_PATH");
export const SITES_URL = encodeURI(`${SPACE_BASE_URL}${SPACE_BASE_PATH}`);
// Live App Base Url
export const LIVE_BASE_URL = getEnvVar("VITE_LIVE_BASE_URL");
export const LIVE_BASE_PATH = getEnvVar("VITE_LIVE_BASE_PATH");
export const LIVE_URL = encodeURI(`${LIVE_BASE_URL}${LIVE_BASE_PATH}`);
// Web App Base Url
export const WEB_BASE_URL = getEnvVar("VITE_WEB_BASE_URL");
export const WEB_BASE_PATH = getEnvVar("VITE_WEB_BASE_PATH");
export const WEB_URL = encodeURI(`${WEB_BASE_URL}${WEB_BASE_PATH}`);
// plane website url
export const WEBSITE_URL = getEnvVar("VITE_WEBSITE_URL", "https://plane.so");
// support email
export const SUPPORT_EMAIL = getEnvVar("VITE_SUPPORT_EMAIL", "support@plane.so");
// marketing links
export const MARKETING_PRICING_PAGE_LINK = "https://plane.so/pricing";
export const MARKETING_CONTACT_US_PAGE_LINK = "https://plane.so/contact";
export const MARKETING_PLANE_ONE_PAGE_LINK = "https://plane.so/one";
