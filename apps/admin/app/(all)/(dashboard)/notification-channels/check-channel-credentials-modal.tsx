/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
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
import type { TInstanceNotificationChannel } from "@plane/types";

type Props = {
  channel: TInstanceNotificationChannel;
  channelName: string;
  isOpen: boolean;
  handleClose: () => void;
};

enum ECredentialsCheckSteps {
  CHECK_CREDENTIALS = "CHECK_CREDENTIALS",
  SUCCESS = "SUCCESS",
  FAILED = "FAILED",
}

const instanceService = new InstanceService();

/**
 * Runs the instance level credentials check for a single notification channel and
 * surfaces the message returned by the API when the provider rejects the credentials.
 */
export function CheckChannelCredentialsModal(props: Props) {
  const { channel, channelName, isOpen, handleClose } = props;

  // state
  const [checkStep, setCheckStep] = useState<ECredentialsCheckSteps>(ECredentialsCheckSteps.CHECK_CREDENTIALS);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");

  // reset state
  const resetState = () => {
    setCheckStep(ECredentialsCheckSteps.CHECK_CREDENTIALS);
    setIsLoading(false);
    setError("");
  };

  const handleSubmit = async (e: React.MouseEvent<HTMLButtonElement, MouseEvent>) => {
    e.preventDefault();

    setIsLoading(true);
    await instanceService
      .checkNotificationChannelCredentials(channel)
      .then(() => {
        setCheckStep(ECredentialsCheckSteps.SUCCESS);
        return;
      })
      .catch((err) => {
        setError(err?.error || `We could not verify the ${channelName} credentials.`);
        setCheckStep(ECredentialsCheckSteps.FAILED);
      })
      .finally(() => {
        setIsLoading(false);
      });
  };

  return (
    <Dialog
      open={isOpen}
      onOpenChange={(open) => {
        if (!open) handleClose();
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
                {checkStep === ECredentialsCheckSteps.CHECK_CREDENTIALS && `Check ${channelName} credentials`}
                {checkStep === ECredentialsCheckSteps.SUCCESS && "Credentials are valid"}
                {checkStep === ECredentialsCheckSteps.FAILED && "Check failed"}
              </DialogTitle>
            </DialogHeading>
          </DialogHeader>
          <DialogBody>
            {checkStep === ECredentialsCheckSteps.CHECK_CREDENTIALS && (
              <div className="flex flex-col gap-y-4 text-13">
                <p>
                  This verifies the {channelName} credentials that are currently saved on this instance. Save your
                  changes before running the check.
                </p>
              </div>
            )}
            {checkStep === ECredentialsCheckSteps.SUCCESS && (
              <div className="flex flex-col gap-y-4 text-13">
                <p>Plane could reach {channelName} with the saved credentials.</p>
                <p>Users can now subscribe to {channelName} notifications from their profile settings.</p>
              </div>
            )}
            {checkStep === ECredentialsCheckSteps.FAILED && (
              <div className="flex flex-col gap-y-4 text-13">
                <p className="text-13 text-danger-primary">{error}</p>
                <p>Review the credentials, save them and run the check again.</p>
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
            tabIndex={0}
            label={checkStep === ECredentialsCheckSteps.CHECK_CREDENTIALS ? "Cancel" : "Close"}
          />
          {checkStep === ECredentialsCheckSteps.CHECK_CREDENTIALS && (
            <Button
              variant="primary"
              size="md"
              stretch="auto"
              loading={isLoading}
              onClick={handleSubmit}
              tabIndex={0}
              label={isLoading ? "Checking credentials" : "Check credentials"}
            />
          )}
        </DialogActions>
      </DialogContent>
    </Dialog>
  );
}
