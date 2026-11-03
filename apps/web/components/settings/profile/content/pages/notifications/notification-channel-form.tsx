/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useCallback, useEffect, useState } from "react";
// plane imports
import { useTranslation } from "@plane/i18n";
import { setToast } from "@plane/blocks/toast";
import type {
  INotificationChannelTestErrorResponse,
  INotificationChannelUpdatePayload,
  IUserNotificationChannel,
  IUserNotificationChannels,
  TNotificationEvent,
  TNotificationEventPreferences,
} from "@plane/types";
import { Field } from "@makeplane/propel/components/field";
import { Input, InputGroup } from "@makeplane/propel/components/input";
import { Switch } from "@makeplane/propel/components/switch";
import { Button } from "@makeplane/propel/components/button";
import { AlertCircleOutline } from "@makeplane/propel/icons";
// components
import { SettingsControlItem } from "@/components/settings/control-item";
// services
import { UserService } from "@/services/user.service";

/**
 * Client side mirror of the server side validation so an obviously wrong address never leaves the
 * browser, while still surfacing whatever the API answers when it disagrees.
 */
const MOBILE_NUMBER_REGEX = /^09\d{9}$|^989\d{9}$/;
const BALE_CHAT_ID_REGEX = /^(?:\d{1,20}|@[A-Za-z][A-Za-z0-9_]{2,31})$/;

/**
 * Ordering and copy of the notification events. Labels reuse the keys the email channel already
 * ships so both channels read identically.
 */
const NOTIFICATION_EVENT_ITEMS: { event: TNotificationEvent; labelKey: string; descriptionKey: string }[] = [
  { event: "property_change", labelKey: "property_changes", descriptionKey: "property_changes_description" },
  { event: "state_change", labelKey: "state_change", descriptionKey: "state_change_description" },
  { event: "comment", labelKey: "comments", descriptionKey: "comments_description" },
  { event: "mention", labelKey: "mentions", descriptionKey: "mentions_description" },
  { event: "issue_completed", labelKey: "issue_completed", descriptionKey: "issue_completed_description" },
];

// services
const userService = new UserService();

/**
 * The API rejects a mutation with `{ error, code }`, where `error` is already written for the end
 * user. Prefer it over the generic fallback so the reason actually reaches the toast.
 */
const getApiErrorMessage = (error: unknown, fallback: string): string => {
  const message = (error as INotificationChannelTestErrorResponse | undefined)?.error;
  return typeof message === "string" && message.trim().length > 0 ? message : fallback;
};

type Props = {
  channel: IUserNotificationChannel;
  onAggregateUpdate: (aggregate: IUserNotificationChannels) => void;
  onRevalidate: () => Promise<unknown>;
};

export function NotificationChannelForm(props: Props) {
  const { channel, onAggregateUpdate, onRevalidate } = props;
  // translation
  const { t } = useTranslation();
  // address state
  const [addressValue, setAddressValue] = useState<string>(channel.address ?? "");
  const [addressError, setAddressError] = useState<string | null>(null);
  const [isAddressDirty, setIsAddressDirty] = useState<boolean>(false);
  const [isSavingAddress, setIsSavingAddress] = useState<boolean>(false);
  // channel / event / test state
  const [isTogglingChannel, setIsTogglingChannel] = useState<boolean>(false);
  const [pendingEvent, setPendingEvent] = useState<TNotificationEvent | null>(null);
  const [isTestingChannel, setIsTestingChannel] = useState<boolean>(false);
  const [eventPreferences, setEventPreferences] = useState<TNotificationEventPreferences>(channel.preferences);

  // derived values
  const addressLabel = t(`account_settings.notifications.channels.address_label_${channel.address_field}`);
  const isChannelConfigured = channel.provider_configured;
  const hasSavedAddress = (channel.address ?? "").trim().length > 0;

  // keep the editable address in sync with the server record without clobbering in-progress typing
  useEffect(() => {
    if (isAddressDirty) return;
    setAddressValue(channel.address ?? "");
    setAddressError(null);
  }, [channel.address, isAddressDirty]);

  // adopt the persisted preferences whenever the aggregate is refreshed
  useEffect(() => {
    setEventPreferences(channel.preferences);
  }, [channel.preferences]);

  const validateAddress = useCallback(
    (value: string): string | null => {
      const trimmedValue = value.trim();
      if (trimmedValue.length === 0) {
        return t(
          channel.address_field === "mobile_number"
            ? "account_settings.notifications.channels.invalid_mobile_number"
            : "account_settings.notifications.channels.invalid_bale_chat_id"
        );
      }
      const isValid =
        channel.address_field === "mobile_number"
          ? MOBILE_NUMBER_REGEX.test(trimmedValue)
          : BALE_CHAT_ID_REGEX.test(trimmedValue);
      if (isValid) return null;
      return t(
        channel.address_field === "mobile_number"
          ? "account_settings.notifications.channels.invalid_mobile_number"
          : "account_settings.notifications.channels.invalid_bale_chat_id"
      );
    },
    [channel.address_field, t]
  );

  /**
   * Builds the update body. The address key is whatever the backend reported as `address_field`,
   * so the client never hard codes which field the channel expects.
   */
  const buildUpdatePayload = useCallback(
    (data: { address?: string; isEnabled?: boolean }): INotificationChannelUpdatePayload => ({
      channel: channel.channel,
      ...(data.isEnabled === undefined ? {} : { is_enabled: data.isEnabled }),
      ...(data.address === undefined ? {} : { [channel.address_field]: data.address }),
    }),
    [channel.address_field, channel.channel]
  );

  const handleSaveAddress = useCallback(
    async (value: string): Promise<boolean> => {
      const validationError = validateAddress(value);
      if (validationError) {
        setAddressError(validationError);
        return false;
      }
      setAddressError(null);
      setIsSavingAddress(true);
      try {
        const aggregate = await userService.updateCurrentUserNotificationChannel(
          buildUpdatePayload({ address: value.trim() })
        );
        setIsAddressDirty(false);
        setAddressValue(value.trim());
        onAggregateUpdate(aggregate);
        setToast({
          title: t("success"),
          type: "success",
          message: t("account_settings.notifications.channels.address_saved_successfully", {
            address_label: addressLabel,
          }),
        });
        return true;
      } catch (error) {
        setToast({
          title: t("error"),
          type: "error",
          message: getApiErrorMessage(error, t("account_settings.notifications.channels.failed_to_save_address")),
        });
        return false;
      } finally {
        setIsSavingAddress(false);
      }
    },
    [addressLabel, buildUpdatePayload, onAggregateUpdate, t, validateAddress]
  );

  const handleAddressSaveClick = useCallback(async () => {
    setIsAddressDirty(false);
    await handleSaveAddress(addressValue);
  }, [addressValue, handleSaveAddress]);

  const handleChannelToggle = useCallback(
    async (isEnabled: boolean) => {
      // an enabled channel without a stored address can never deliver, so persist it first
      if (isEnabled && !hasSavedAddress) {
        const saved = await handleSaveAddress(addressValue);
        if (!saved) {
          setToast({
            title: t("error"),
            type: "error",
            message: t("account_settings.notifications.channels.address_required_before_enabling", {
              address_label: addressLabel,
            }),
          });
          return;
        }
      }

      setIsTogglingChannel(true);
      try {
        const aggregate = await userService.updateCurrentUserNotificationChannel(buildUpdatePayload({ isEnabled }));
        onAggregateUpdate(aggregate);
        setToast({
          title: t("success"),
          type: "success",
          message: t(
            isEnabled
              ? "account_settings.notifications.channels.channel_enabled_successfully"
              : "account_settings.notifications.channels.channel_disabled_successfully"
          ),
        });
      } catch (error) {
        setToast({
          title: t("error"),
          type: "error",
          message: getApiErrorMessage(error, t("account_settings.notifications.channels.failed_to_update_channel")),
        });
      } finally {
        setIsTogglingChannel(false);
      }
    },
    [addressLabel, addressValue, buildUpdatePayload, handleSaveAddress, hasSavedAddress, onAggregateUpdate, t]
  );

  const handleEventToggle = useCallback(
    async (event: TNotificationEvent, isEnabled: boolean) => {
      const previousPreferences = eventPreferences;
      setEventPreferences((current) => ({ ...current, [event]: isEnabled }));
      setPendingEvent(event);
      try {
        await userService.updateCurrentUserNotificationChannelPreference({
          channel: channel.channel,
          event,
          is_enabled: isEnabled,
        });
        await onRevalidate();
        setToast({
          title: t("success"),
          type: "success",
          message: t("account_settings.notifications.channels.preference_updated_successfully"),
        });
      } catch (error) {
        setEventPreferences(previousPreferences);
        setToast({
          title: t("error"),
          type: "error",
          message: getApiErrorMessage(error, t("account_settings.notifications.channels.failed_to_update_preference")),
        });
      } finally {
        setPendingEvent(null);
      }
    },
    [channel.channel, eventPreferences, onRevalidate, t]
  );

  const handleTestNotification = useCallback(async () => {
    setIsTestingChannel(true);
    try {
      await userService.sendCurrentUserNotificationChannelTest({ channel: channel.channel });
      setToast({
        title: t("success"),
        type: "success",
        message: t("account_settings.notifications.channels.test_notification_sent_successfully"),
      });
    } catch (error) {
      setToast({
        title: t("error"),
        type: "error",
        message: getApiErrorMessage(
          error,
          t("account_settings.notifications.channels.failed_to_send_test_notification")
        ),
      });
    } finally {
      setIsTestingChannel(false);
      await onRevalidate();
    }
  }, [channel.channel, onRevalidate, t]);

  return (
    <div className="flex flex-col gap-4 rounded-md border border-subtle-1 bg-surface-1 p-4">
      {/* channel identity */}
      <div className="flex flex-col gap-1">
        <h3 className="text-body-md-medium text-primary">
          {t(`account_settings.notifications.channels.${channel.channel.toLowerCase()}_title`)}
        </h3>
        <p className="text-caption-md-regular text-secondary">
          {t(`account_settings.notifications.channels.${channel.channel.toLowerCase()}_description`)}
        </p>
      </div>

      {/* provider configuration status */}
      <div
        className={`flex items-start gap-2 rounded-md border px-3 py-2 ${
          isChannelConfigured ? "border-subtle-1 bg-surface-2" : "border-subtle-1 bg-warning-subtle"
        }`}
      >
        <AlertCircleOutline
          className={`h-4 w-4 shrink-0 ${isChannelConfigured ? "text-tertiary" : "text-warning-primary"}`}
          aria-hidden="true"
        />
        <p className={`text-caption-md-regular ${isChannelConfigured ? "text-secondary" : "text-warning-primary"}`}>
          {isChannelConfigured
            ? t("account_settings.notifications.channels.provider_configured")
            : t("account_settings.notifications.channels.provider_not_configured")}
        </p>
      </div>

      {/* delivery address */}
      <div className="flex flex-col gap-1">
        <h4 className="text-13 font-medium text-secondary">{addressLabel}</h4>
        <div className="flex w-full flex-col items-start gap-2 sm:flex-row sm:items-start">
          <div className="w-full">
            <Field name={channel.address_field} invalid={Boolean(addressError)}>
              <InputGroup size="2xl">
                <Input
                  size="2xl"
                  id={`notification-channel-${channel.address_field}`}
                  name={channel.address_field}
                  type="text"
                  value={addressValue}
                  placeholder={t(
                    `account_settings.notifications.channels.address_placeholder_${channel.address_field}`
                  )}
                  autoComplete="off"
                  onChange={(event) => {
                    setIsAddressDirty(true);
                    setAddressError(null);
                    setAddressValue(event.target.value);
                  }}
                />
              </InputGroup>
            </Field>
          </div>
          <Button
            variant="secondary"
            size="sm"
            stretch="auto"
            label={
              isSavingAddress
                ? t("account_settings.notifications.channels.saving_address")
                : t("account_settings.notifications.channels.save_address")
            }
            loading={isSavingAddress}
            onClick={() => void handleAddressSaveClick()}
          />
        </div>
        <p className="text-11 text-secondary">
          {t(`account_settings.notifications.channels.address_helper_${channel.address_field}`)}
        </p>
        {addressError && <span className="text-11 text-danger-primary">{addressError}</span>}
      </div>

      <div className="border-t border-subtle-1" />

      {/* channel master switch */}
      <SettingsControlItem
        title={t("account_settings.notifications.channels.enable_channel")}
        description={t("account_settings.notifications.channels.enable_channel_description")}
        control={
          <Switch
            size="sm"
            checked={channel.is_enabled}
            disabled={isTogglingChannel}
            onCheckedChange={(newValue) => void handleChannelToggle(newValue)}
            aria-label={t("account_settings.notifications.channels.enable_channel")}
          />
        }
      />

      {/* per event switches */}
      {NOTIFICATION_EVENT_ITEMS.map((item) => (
        <SettingsControlItem
          key={`${channel.channel}-${item.event}`}
          title={t(item.labelKey)}
          description={t(item.descriptionKey)}
          control={
            <Switch
              size="sm"
              checked={eventPreferences[item.event]}
              disabled={pendingEvent === item.event}
              onCheckedChange={(newValue) => void handleEventToggle(item.event, newValue)}
              aria-label={t(item.labelKey)}
            />
          }
        />
      ))}

      <div className="border-t border-subtle-1" />

      {/* delivery verification */}
      <SettingsControlItem
        title={t("account_settings.notifications.channels.test_notification")}
        description={t("account_settings.notifications.channels.test_notification_description")}
        control={
          <Button
            variant="secondary"
            size="sm"
            stretch="auto"
            label={
              isTestingChannel
                ? t("account_settings.notifications.channels.sending_test")
                : t("account_settings.notifications.channels.test_notification")
            }
            loading={isTestingChannel}
            disabled={!isChannelConfigured || !hasSavedAddress}
            onClick={() => void handleTestNotification()}
          />
        }
      />

      {/* last delivery outcome */}
      <div className="flex flex-col gap-1">
        {channel.last_status && (
          <p className="text-11 text-secondary">
            {t("account_settings.notifications.channels.last_status", { status: channel.last_status })}
          </p>
        )}
        {channel.last_delivered_at && (
          <p className="text-11 text-secondary">
            {t("account_settings.notifications.channels.last_delivered_at", {
              date: new Date(channel.last_delivered_at).toLocaleString(),
            })}
          </p>
        )}
        <p className="text-11 text-secondary">
          {channel.is_verified
            ? t("account_settings.notifications.channels.verified")
            : t("account_settings.notifications.channels.not_verified")}
        </p>
        {Boolean(channel.last_error) && (
          <p className="text-11 text-danger-primary">
            {t("account_settings.notifications.channels.last_error", { error: channel.last_error })}
          </p>
        )}
      </div>
    </div>
  );
}
