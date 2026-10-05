/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// Delivery channels other than email, configured once per instance in God Mode.
export type TInstanceNotificationChannel = "SMS" | "BALE";

export type TInstanceNotificationChannelConfigurationKeys =
  // Kavenegar
  | "KAVENEGAR_API_KEY"
  | "KAVENEGAR_SENDER_LINE"
  // Bale
  | "BALE_BOT_TOKEN"
  | "BALE_BOT_USERNAME"
  | "BALE_WEBHOOK_BASE_URL"
  | "BALE_WEBHOOK_SECRET";

/**
 * Result of POST /api/instances/notification-channel-credentials-check/
 * A failed check responds with HTTP 400 and the same shape plus `error`.
 */
export type INotificationChannelCredentialsCheck = {
  channel: TInstanceNotificationChannel;
  is_configured: boolean;
  error?: string;
};

/**
 * Result of POST /api/instances/bale-webhook/register/ and POST /api/instances/bale-webhook/status/
 * A rejected request responds with HTTP 400 and `{"error": "<message returned by the API>"}` instead.
 */
export type IBaleWebhookState = {
  channel: "BALE";
  is_registered: boolean;
  webhook_url: string;
  bot_username: string;
  bot_id: string;
  bot_first_name?: string;
};

/**
 * Result of POST /api/instances/bale-webhook/unregister/
 */
export type IBaleWebhookUnregistration = {
  channel: "BALE";
  is_registered: boolean;
};
