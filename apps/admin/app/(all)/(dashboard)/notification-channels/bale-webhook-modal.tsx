/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import type { MouseEvent as ReactMouseEvent } from "react";
// plane imports
import { Button } from "@makeplane/propel/components/button";
import {
  Dialog,
  DialogActions,
  DialogBody,
  DialogContent,
  DialogHeader,
  DialogHeading,
  DialogMain,
  DialogTitle,
} from "@makeplane/propel/components/dialog";
import { InstanceService } from "@plane/services";
import type { IBaleWebhookState } from "@plane/types";
import { cn } from "@plane/utils";

export type TBaleWebhookAction = "REGISTER" | "STATUS" | "UNREGISTER";

type Props = {
  action: TBaleWebhookAction;
  isOpen: boolean;
  isBotTokenConfigured: boolean;
  handleClose: () => void;
  onPendingChange?: (isPending: boolean) => void;
  onRegistered?: (state: IBaleWebhookState) => void;
};

enum EBaleWebhookSteps {
  CONFIRM = "CONFIRM",
  SUCCESS = "SUCCESS",
  FAILED = "FAILED",
}

const ACTION_COPY = {
  REGISTER: {
    title: "Register the webhook on Bale",
    runningLabel: "Registering webhook",
    actionLabel: "Register webhook",
    successTitle: "Webhook registered",
    successBody: "Bale now delivers every update to Plane through the webhook below.",
    failureTitle: "Registration failed",
  },
  STATUS: {
    title: "Bale webhook status",
    runningLabel: "Checking status",
    actionLabel: "Check status",
    successTitle: "Webhook status",
    successBody: "This is what the Bale bot reports right now.",
    failureTitle: "Status check failed",
  },
  UNREGISTER: {
    title: "Delete the webhook from Bale",
    runningLabel: "Deleting webhook",
    actionLabel: "Delete webhook",
    successTitle: "Webhook deleted",
    successBody: "The webhook URL was removed from the Bale bot.",
    failureTitle: "Deletion failed",
  },
} as const;

const instanceService = new InstanceService();

/**
 * Renders whether the bot currently points back at this Plane instance.
 */
function WebhookRegistrationBadge(props: { isRegistered: boolean }) {
  const { isRegistered } = props;

  return (
    <span
      className={cn(
        "rounded-full border border-subtle px-2 py-0.5 text-11 font-medium whitespace-nowrap",
        isRegistered ? "text-success-primary" : "text-tertiary"
      )}
    >
      {isRegistered ? "Registered" : "Not registered"}
    </span>
  );
}

/**
 * Drives one of the instance level Bale webhook endpoints (register, unregister, status) from God Mode
 * and surfaces the message returned by the API when Bale rejects the call.
 */
export function BaleWebhookModal(props: Props) {
  const { action, isOpen, isBotTokenConfigured, handleClose, onPendingChange, onRegistered } = props;

  // state
  const [step, setStep] = useState<EBaleWebhookSteps>(EBaleWebhookSteps.CONFIRM);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<IBaleWebhookState | null>(null);

  // the bot token is what register authenticates with, so guard before touching Bale
  const isBlocked = action === "REGISTER" && !isBotTokenConfigured;
  const copy = ACTION_COPY[action];

  // reset state
  const resetState = () => {
    setStep(EBaleWebhookSteps.CONFIRM);
    setIsLoading(false);
    setError("");
    setResult(null);
  };

  const runAction = (): Promise<IBaleWebhookState> => {
    if (action === "REGISTER") return instanceService.registerBaleWebhook();
    if (action === "STATUS") return instanceService.baleWebhookStatus();
    // unregister answers with the smaller shape, so pad it to keep one result type in the UI
    return instanceService
      .unregisterBaleWebhook()
      .then((response) => ({ ...response, webhook_url: "", bot_username: "", bot_id: "" }));
  };

  const handleSubmit = async (e: ReactMouseEvent<HTMLButtonElement>) => {
    e.preventDefault();
    if (isBlocked || isLoading) return;

    setIsLoading(true);
    onPendingChange?.(true);
    setError("");
    await runAction()
      .then((response) => {
        setResult(response);
        setStep(EBaleWebhookSteps.SUCCESS);
        if (action === "REGISTER") onRegistered?.(response);
        return;
      })
      .catch((err) => {
        setError(err?.error || `We could not run the ${action.toLowerCase()} request against Bale.`);
        setStep(EBaleWebhookSteps.FAILED);
      })
      .finally(() => {
        setIsLoading(false);
        onPendingChange?.(false);
      });
  };

  return (
    <Dialog
      open={isOpen}
      onOpenChange={(open) => {
        // do not let a running call be interrupted halfway through
        if (!open && !isLoading) handleClose();
      }}
      // reset after the close animation so the content does not flip back while fading out
      onOpenChangeComplete={(open) => {
        if (!open) resetState();
      }}
    >
      <DialogContent size="sm">
        <DialogMain>
          <DialogHeader>
            <DialogHeading>
              <DialogTitle>
                {step === EBaleWebhookSteps.CONFIRM && copy.title}
                {step === EBaleWebhookSteps.SUCCESS && copy.successTitle}
                {step === EBaleWebhookSteps.FAILED && copy.failureTitle}
              </DialogTitle>
            </DialogHeading>
          </DialogHeader>
          <DialogBody>
            {step === EBaleWebhookSteps.CONFIRM && action === "REGISTER" && (
              <div className="flex flex-col gap-y-4 text-13">
                <p>
                  Plane builds the webhook URL from the webhook base URL and the secret saved below, then asks the Bale
                  bot to send every update to it. Leave the secret empty and Plane generates one for you.
                </p>
                {isBotTokenConfigured ? (
                  <p>Only one bot is shared by every member of this instance.</p>
                ) : (
                  <p className="text-danger-primary">
                    The bot token is not saved on this instance yet. Save the bot token before registering the webhook.
                  </p>
                )}
              </div>
            )}
            {step === EBaleWebhookSteps.CONFIRM && action === "STATUS" && (
              <div className="flex flex-col gap-y-4 text-13">
                <p>
                  Asks the Bale bot which webhook it currently delivers to. This only reads the state, it changes
                  nothing.
                </p>
              </div>
            )}
            {step === EBaleWebhookSteps.CONFIRM && action === "UNREGISTER" && (
              <div className="flex flex-col gap-y-4 text-13">
                <p className="text-danger-primary">
                  This removes the webhook from the Bale bot itself. The bot stops delivering updates to Plane and
                  members who already linked their Bale chat stop receiving notifications.
                </p>
                <p>Register the webhook again to restore the delivery. This cannot be undone from here.</p>
              </div>
            )}
            {step === EBaleWebhookSteps.SUCCESS && (
              <div className="flex flex-col gap-y-4 text-13">
                <p>{copy.successBody}</p>
                {result && (
                  <div className="flex flex-col gap-y-2 rounded border border-subtle p-3">
                    <div className="flex items-center justify-between gap-4">
                      <span className="text-11 text-tertiary">Webhook</span>
                      <WebhookRegistrationBadge isRegistered={result.is_registered} />
                    </div>
                    <div className="flex flex-col gap-y-1">
                      <span className="text-11 text-tertiary">Registered URL</span>
                      <span className="font-mono text-11 break-all text-primary">
                        {result.webhook_url || "Not reported"}
                      </span>
                    </div>
                    <div className="flex flex-col gap-y-1">
                      <span className="text-11 text-tertiary">Bot</span>
                      <span className="text-11 text-primary">
                        {result.bot_username || "Not reported"}
                        {result.bot_id ? ` · ${result.bot_id}` : ""}
                      </span>
                    </div>
                  </div>
                )}
              </div>
            )}
            {step === EBaleWebhookSteps.FAILED && (
              <div className="flex flex-col gap-y-4 text-13">
                <p className="text-danger-primary">{error}</p>
                <p>Review the webhook base URL and the secret, save them and run the request again.</p>
              </div>
            )}
          </DialogBody>
        </DialogMain>
        <DialogActions>
          <Button
            variant="secondary"
            size="md"
            stretch="auto"
            onClick={handleClose}
            disabled={isLoading}
            tabIndex={0}
            label={step === EBaleWebhookSteps.CONFIRM ? "Cancel" : "Close"}
          />
          {step === EBaleWebhookSteps.CONFIRM && (
            <Button
              variant={action === "UNREGISTER" ? "danger" : "primary"}
              size="md"
              stretch="auto"
              loading={isLoading}
              onClick={handleSubmit}
              disabled={isBlocked || isLoading}
              tabIndex={0}
              label={isLoading ? copy.runningLabel : copy.actionLabel}
            />
          )}
        </DialogActions>
      </DialogContent>
    </Dialog>
  );
}
