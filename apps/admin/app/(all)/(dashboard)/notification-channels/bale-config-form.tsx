/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useCallback, useState } from "react";
import { useForm } from "react-hook-form";
// plane imports
import { Button } from "@makeplane/propel/components/button";
import type { IBaleWebhookState, IFormattedInstanceConfiguration } from "@plane/types";
import { ControllerInput } from "@/components/common/controller-input";
import { setToast } from "@plane/blocks/toast";
import { useInstance } from "@/hooks/store";
// local imports
import { BaleWebhookModal } from "./bale-webhook-modal";
import type { TBaleWebhookAction } from "./bale-webhook-modal";
import { ChannelConfiguredStatus } from "./channel-configured-status";
import { CheckChannelCredentialsModal } from "./check-channel-credentials-modal";
import { generateWebhookSecret, WebhookSecretField } from "./webhook-secret-field";

type Props = {
  config: IFormattedInstanceConfiguration;
  isConfigured: boolean;
};

type BaleFormValues = Record<
  "BALE_BOT_TOKEN" | "BALE_BOT_USERNAME" | "BALE_WEBHOOK_BASE_URL" | "BALE_WEBHOOK_SECRET",
  string
>;

const MISSING_BOT_TOKEN_WARNING =
  "The Bale bot token is not saved on this instance yet. Save the bot token before registering the webhook.";

/**
 * Instance level Bale bot settings.
 * One bot is shared by every member of the instance: members link their own Bale chat from their
 * profile notification settings with a one time pairing code, never by entering a chat id here.
 */
export function InstanceBaleConfigForm(props: Props) {
  const { config, isConfigured } = props;

  const { updateInstanceConfigurations, fetchInstanceInfo } = useInstance();
  const [isCheckModalOpen, setIsCheckModalOpen] = useState(false);
  const [webhookAction, setWebhookAction] = useState<TBaleWebhookAction | null>(null);
  const [isWebhookPending, setIsWebhookPending] = useState(false);

  const {
    handleSubmit,
    control,
    getValues,
    setValue,
    formState: { errors, isSubmitting },
  } = useForm<BaleFormValues>({
    defaultValues: {
      BALE_BOT_TOKEN: config.BALE_BOT_TOKEN ?? "",
      BALE_BOT_USERNAME: config.BALE_BOT_USERNAME ?? "",
      BALE_WEBHOOK_BASE_URL: config.BALE_WEBHOOK_BASE_URL ?? "",
      BALE_WEBHOOK_SECRET: config.BALE_WEBHOOK_SECRET ?? "",
    },
  });

  const isBusy = isSubmitting || isWebhookPending;

  const onSubmit = async (formData: BaleFormValues) => {
    await updateInstanceConfigurations({
      BALE_BOT_TOKEN: formData.BALE_BOT_TOKEN,
      BALE_BOT_USERNAME: formData.BALE_BOT_USERNAME,
      BALE_WEBHOOK_BASE_URL: formData.BALE_WEBHOOK_BASE_URL,
      BALE_WEBHOOK_SECRET: formData.BALE_WEBHOOK_SECRET,
    })
      .then(() => fetchInstanceInfo())
      .then(() =>
        setToast({
          type: "success",
          title: "Success",
          message: "Bale bot settings updated successfully",
        })
      )
      .catch((err) => {
        console.error(err);
        setToast({
          type: "error",
          title: "Bale bot settings not updated",
          message:
            typeof err?.error === "string" ? err.error : "Failed to update the Bale bot settings. Please try again.",
        });
      });
  };

  const handleGenerateSecret = () => {
    setValue("BALE_WEBHOOK_SECRET", generateWebhookSecret());
    setToast({
      type: "info",
      title: "Secret generated",
      message: "Save the changes to store this webhook secret on the instance.",
    });
  };

  // the backend reads the bot username from Bale itself, so adopt it when the field was left empty
  const handleRegistered = useCallback(
    (state: IBaleWebhookState) => {
      if (!state.bot_username) return;
      if (getValues("BALE_BOT_USERNAME")) return;
      setValue("BALE_BOT_USERNAME", state.bot_username, { shouldDirty: true });
      setToast({
        type: "info",
        title: "Bot username filled",
        message: "The bot username returned by Bale was written into the form. Save the changes to store it.",
      });
    },
    [getValues, setValue]
  );

  // register needs a bot token, warn instead of sending a request the API is bound to reject
  const openWebhookModal = (action: TBaleWebhookAction) => {
    if (action === "REGISTER" && !isConfigured) {
      setToast({ type: "warning", title: "Bot token missing", message: MISSING_BOT_TOKEN_WARNING });
      return;
    }
    setWebhookAction(action);
  };

  return (
    <div className="border-b border-subtle pb-8">
      <div className="flex items-start justify-between gap-4 pb-6">
        <div className="space-y-1">
          <h3 className="text-13 font-medium text-primary">Bale bot</h3>
          <p className="text-11 font-regular text-tertiary">
            Sends notifications in Bale through a single bot that this instance owns. Members open that bot in Bale and
            link their own chat with a one time pairing code from their profile notification settings.
            <a
              href="https://docs.bale.ai/"
              target="_blank"
              rel="noreferrer"
              className="ml-1 text-accent-primary hover:underline"
            >
              Docs
            </a>
          </p>
        </div>
        <ChannelConfiguredStatus isConfigured={isConfigured} />
      </div>

      <form onSubmit={handleSubmit(onSubmit)}>
        <div className="grid-col grid w-full max-w-4xl grid-cols-1 items-start justify-between gap-10 lg:grid-cols-2">
          <ControllerInput<BaleFormValues>
            name="BALE_BOT_TOKEN"
            control={control}
            type="password"
            label="Bot token"
            placeholder="1234567890:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
            description="The token that @BotFather hands out when the bot is created"
            error={Boolean(errors.BALE_BOT_TOKEN)}
            required
          />
          <ControllerInput<BaleFormValues>
            name="BALE_BOT_USERNAME"
            control={control}
            type="text"
            label="Bot username"
            placeholder="@my_plane_bot"
            description="The bot every member is told to open in Bale. Registering the webhook fills this in when it is empty."
            error={Boolean(errors.BALE_BOT_USERNAME)}
            required={false}
          />
        </div>

        <div className="w-full max-w-4xl pt-6">
          <ControllerInput<BaleFormValues>
            name="BALE_WEBHOOK_BASE_URL"
            control={control}
            type="text"
            label="Webhook base URL"
            placeholder="https://plane.example.com"
            description="Public and https, so Bale can reach it. Leave it empty to use the web URL of the application. On a local install Bale cannot reach localhost, so a publicly reachable address is required."
            error={Boolean(errors.BALE_WEBHOOK_BASE_URL)}
            required={false}
          />
        </div>

        <div className="w-full max-w-4xl pt-6">
          <WebhookSecretField<BaleFormValues>
            control={control}
            name="BALE_WEBHOOK_SECRET"
            label="Webhook secret"
            placeholder="A strong random string"
            description="Only this instance and Bale know the webhook URL. Generate one, or leave it empty and the API creates and stores one when the webhook is registered."
            error={Boolean(errors.BALE_WEBHOOK_SECRET)}
            isSecretConfigured={Boolean(config.BALE_WEBHOOK_SECRET)}
            isGenerateDisabled={isBusy}
            onGenerate={handleGenerateSecret}
          />
        </div>

        <div className="flex max-w-4xl flex-wrap items-center gap-4 py-1 pt-8">
          <Button
            variant="primary"
            size="md"
            stretch="auto"
            type="submit"
            loading={isSubmitting}
            disabled={isBusy}
            tabIndex={0}
            label="Save changes"
          />
          <Button
            variant="tertiary"
            size="md"
            stretch="auto"
            type="button"
            onClick={() => setIsCheckModalOpen(true)}
            disabled={isBusy}
            tabIndex={0}
            label="Check credentials"
          />
          <Button
            variant="secondary"
            size="md"
            stretch="auto"
            type="button"
            onClick={() => openWebhookModal("REGISTER")}
            disabled={isBusy}
            tabIndex={0}
            label="Register webhook"
          />
          <Button
            variant="secondary"
            size="md"
            stretch="auto"
            type="button"
            onClick={() => openWebhookModal("STATUS")}
            disabled={isBusy}
            tabIndex={0}
            label="Webhook status"
          />
          <Button
            variant="danger-outline"
            size="md"
            stretch="auto"
            type="button"
            onClick={() => openWebhookModal("UNREGISTER")}
            disabled={isBusy}
            tabIndex={0}
            label="Delete webhook"
          />
        </div>
      </form>

      <CheckChannelCredentialsModal
        channel="BALE"
        channelName="Bale bot"
        isOpen={isCheckModalOpen}
        handleClose={() => setIsCheckModalOpen(false)}
      />

      <BaleWebhookModal
        action={webhookAction ?? "STATUS"}
        isOpen={webhookAction !== null}
        isBotTokenConfigured={isConfigured}
        handleClose={() => setWebhookAction(null)}
        onPendingChange={setIsWebhookPending}
        onRegistered={handleRegistered}
      />
    </div>
  );
}
