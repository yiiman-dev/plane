/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { useForm } from "react-hook-form";
// plane imports
import { Button } from "@makeplane/propel/components/button";
import type { IFormattedInstanceConfiguration } from "@plane/types";
import { ControllerInput } from "@/components/common/controller-input";
import { setToast } from "@plane/blocks/toast";
import { useInstance } from "@/hooks/store";
// local imports
import { ChannelConfiguredStatus } from "./channel-configured-status";
import { CheckChannelCredentialsModal } from "./check-channel-credentials-modal";

type Props = {
  config: IFormattedInstanceConfiguration;
  isConfigured: boolean;
};

type KavenegarFormValues = Record<"KAVENEGAR_API_KEY" | "KAVENEGAR_SENDER_LINE", string>;

const kavenegarFields: {
  name: keyof KavenegarFormValues;
  label: string;
  placeholder: string;
  type: "text" | "password";
  description: string;
  required: boolean;
}[] = [
  {
    name: "KAVENEGAR_API_KEY",
    label: "API key",
    placeholder: "Your Kavenegar API key",
    type: "password",
    description: "Found in your Kavenegar panel under Account > API",
    required: true,
  },
  {
    name: "KAVENEGAR_SENDER_LINE",
    label: "Sender line",
    placeholder: "20006535",
    type: "text",
    description: "The dedicated line that sends the messages, for example 20006535",
    required: true,
  },
];

/**
 * Instance level Kavenegar SMS settings.
 */
export function InstanceKavenegarConfigForm(props: Props) {
  const { config, isConfigured } = props;

  const { updateInstanceConfigurations, fetchInstanceInfo } = useInstance();
  const [isCheckModalOpen, setIsCheckModalOpen] = useState(false);

  const {
    handleSubmit,
    control,
    formState: { errors, isSubmitting },
  } = useForm<KavenegarFormValues>({
    defaultValues: {
      KAVENEGAR_API_KEY: config.KAVENEGAR_API_KEY ?? "",
      KAVENEGAR_SENDER_LINE: config.KAVENEGAR_SENDER_LINE ?? "",
    },
  });

  const onSubmit = async (formData: KavenegarFormValues) => {
    await updateInstanceConfigurations({
      KAVENEGAR_API_KEY: formData.KAVENEGAR_API_KEY,
      KAVENEGAR_SENDER_LINE: formData.KAVENEGAR_SENDER_LINE,
    })
      .then(() => fetchInstanceInfo())
      .then(() =>
        setToast({
          type: "success",
          title: "Success",
          message: "Kavenegar SMS settings updated successfully",
        })
      )
      .catch((err) => {
        console.error(err);
        setToast({
          type: "error",
          title: "Kavenegar SMS settings not updated",
          message:
            typeof err?.error === "string"
              ? err.error
              : "Failed to update the Kavenegar SMS settings. Please try again.",
        });
      });
  };

  return (
    <div className="border-b border-subtle pb-8">
      <div className="flex items-start justify-between gap-4 pb-6">
        <div className="space-y-1">
          <h3 className="text-13 font-medium text-primary">Kavenegar SMS</h3>
          <p className="text-11 font-regular text-tertiary">
            Sends notifications as an SMS through Kavenegar. Members subscribe to the events they care about in their
            profile notification settings and need a verified mobile number.
            <a
              href="https://kavenegar.com/docs"
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
          {kavenegarFields.map((field) => (
            <ControllerInput<KavenegarFormValues>
              key={field.name}
              name={field.name}
              control={control}
              type={field.type}
              label={field.label}
              placeholder={field.placeholder}
              description={field.description}
              error={Boolean(errors[field.name])}
              required={field.required}
            />
          ))}
        </div>

        <div className="flex max-w-4xl items-center gap-4 py-1 pt-8">
          <Button
            variant="primary"
            size="md"
            stretch="auto"
            type="submit"
            loading={isSubmitting}
            disabled={isSubmitting}
            tabIndex={0}
            label="Save changes"
          />
          <Button
            variant="tertiary"
            size="md"
            stretch="auto"
            onClick={() => setIsCheckModalOpen(true)}
            tabIndex={0}
            label="Check credentials"
          />
        </div>
      </form>

      <CheckChannelCredentialsModal
        channel="SMS"
        channelName="Kavenegar SMS"
        isOpen={isCheckModalOpen}
        handleClose={() => setIsCheckModalOpen(false)}
      />
    </div>
  );
}
