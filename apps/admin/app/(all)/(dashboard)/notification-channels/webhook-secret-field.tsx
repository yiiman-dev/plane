/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { Control, FieldPath, FieldValues } from "react-hook-form";
// plane imports
import { Button } from "@makeplane/propel/components/button";
import { ControllerInput } from "@/components/common/controller-input";
// local imports
import { ChannelConfiguredStatus } from "./channel-configured-status";

type Props<TFieldValues extends FieldValues = FieldValues> = {
  control: Control<TFieldValues>;
  name: FieldPath<TFieldValues>;
  label: string;
  placeholder: string;
  description: string;
  error: boolean;
  isSecretConfigured: boolean;
  isGenerateDisabled: boolean;
  onGenerate: () => void;
};

const SECRET_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
const SECRET_LENGTH = 48;

/**
 * Builds a random webhook secret the admin can accept as is, instead of inventing one by hand.
 * Bytes above the largest unbiased multiple of the alphabet size are discarded.
 */
export function generateWebhookSecret(length: number = SECRET_LENGTH): string {
  const limit = Math.floor(256 / SECRET_ALPHABET.length) * SECRET_ALPHABET.length;
  let secret = "";

  while (secret.length < length) {
    const bytes = new Uint8Array(length);
    window.crypto.getRandomValues(bytes);
    for (const byte of bytes) {
      if (byte >= limit) continue;
      secret += SECRET_ALPHABET[byte % SECRET_ALPHABET.length];
      if (secret.length === length) break;
    }
  }

  return secret;
}

/**
 * Secret configuration input paired with a configured/not configured badge and a generate button.
 * The saved secret is never rendered, only whether one exists.
 */
export function WebhookSecretField<TFieldValues extends FieldValues = FieldValues>(props: Props<TFieldValues>) {
  const { control, name, label, placeholder, description, error, isSecretConfigured, isGenerateDisabled, onGenerate } =
    props;

  return (
    <div className="flex flex-col gap-1">
      <ControllerInput<TFieldValues>
        name={name}
        control={control}
        type="password"
        label={label}
        placeholder={placeholder}
        description={description}
        error={error}
        required={false}
      />
      <div className="flex items-center justify-between gap-4 pt-2">
        <ChannelConfiguredStatus isConfigured={isSecretConfigured} />
        <Button
          variant="tertiary"
          size="sm"
          stretch="auto"
          type="button"
          onClick={onGenerate}
          disabled={isGenerateDisabled}
          tabIndex={0}
          label="Generate"
        />
      </div>
    </div>
  );
}
