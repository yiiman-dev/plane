/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useCallback, useEffect, useState } from "react";
import { observer } from "mobx-react";
import { useParams } from "next/navigation";
// plane imports
import { EUserPermissions, EUserPermissionsLevel } from "@plane/constants";
import { setToast } from "@plane/blocks/toast";
import { Checkbox } from "@makeplane/propel/components/checkbox";
import { Input } from "@makeplane/propel/components/input";
import { Switch } from "@makeplane/propel/components/switch";
import type { TProjectTimeTrackingSetting, TTimeTrackingDefaultView } from "@plane/types";
import { cn } from "@plane/utils";
// components
import { RadioInput } from "@/components/estimates/radio-select";
import { NotAuthorizedView } from "@/components/auth-screens/not-authorized-view";
import { SettingsBoxedControlItem } from "@/components/settings/boxed-control-item";
import { PageHead } from "@/components/core/page-title";
import { SettingsContentWrapper } from "@/components/settings/content-wrapper";
import { SettingsHeading } from "@/components/settings/heading";
// hooks
import { useProject } from "@/hooks/store/use-project";
import { useUserPermissions } from "@/hooks/store/user";
import { useMember } from "@/hooks/store/use-member";
import { timeTrackingService } from "@/services/time-tracking.service";
import { FeaturesTimeTrackingProjectSettingsHeader } from "./header";

type Props = {
  params?: {
    workspaceSlug?: string;
    projectId?: string;
  };
};

const SUB_PANEL_CLASSNAME = "flex w-full flex-col gap-3 rounded-lg border border-subtle bg-layer-2 px-4 py-3";

const DEFAULT_VIEW_OPTIONS: { key: TTimeTrackingDefaultView; title: string; description: string }[] = [
  {
    key: "grouped_by_date",
    title: "به تفکیک تاریخ",
    description: "دسته‌بندی لاگ‌های هر روز با مجموع زمان کاری آن تاریخ",
  },
  {
    key: "grouped_by_user",
    title: "به تفکیک افراد",
    description: "نمایش سهم هر یک از اعضای تیم در زمان انجام تسک",
  },
  {
    key: "timeline_intervals",
    title: "مقاطع زمانی (تایم‌لاین)",
    description: "فهرست ترتیبی تمامی نوبت‌ها با زمان شروع، پایان و یادداشت",
  },
];

function FeaturesTimeTrackingSettingsPage({ params }: Props) {
  const routerParams = useParams();
  const workspaceSlug = (params?.workspaceSlug || routerParams?.workspaceSlug || "") as string;
  const projectId = (params?.projectId || routerParams?.projectId || "") as string;

  // store hooks
  const { currentProjectDetails, updateProject } = useProject();
  const { workspaceUserInfo, allowPermissions } = useUserPermissions();
  const {
    project: { getProjectMemberIds, fetchProjectMembers },
    getUserDetails,
  } = useMember();

  // states
  const [settings, setSettings] = useState<TProjectTimeTrackingSetting | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  const canPerformProjectAdminActions = allowPermissions([EUserPermissions.ADMIN], EUserPermissionsLevel.PROJECT);

  // Load project members and settings
  const loadData = useCallback(async () => {
    if (!workspaceSlug || !projectId) return;
    try {
      setIsLoading(true);
      await fetchProjectMembers(workspaceSlug, projectId);
      const res = await timeTrackingService.getTimeTrackingSettings(workspaceSlug, projectId);
      setSettings(res);
    } catch (err: any) {
      setToast({
        type: "error",
        title: "خطا",
        message: err?.error || "خطا در دریافت تنظیمات ثبت زمان",
      });
    } finally {
      setIsLoading(false);
    }
  }, [workspaceSlug, projectId, fetchProjectMembers]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleUpdate = async (fields: Partial<TProjectTimeTrackingSetting>) => {
    if (!settings) return;
    try {
      const updated = await timeTrackingService.updateTimeTrackingSettings(workspaceSlug, projectId, fields);
      setSettings(updated);
      if ("is_enabled" in fields) {
        updateProject(workspaceSlug, projectId, {
          is_time_tracking_enabled: fields.is_enabled,
        });
      }
      setToast({
        type: "success",
        title: "موفق",
        message: "تنظیمات با موفقیت ذخیره شد.",
      });
    } catch (err: any) {
      setToast({
        type: "error",
        title: "خطا",
        message: err?.error || "خطا در ذخیره تنظیمات",
      });
    }
  };

  const projectMemberIds = getProjectMemberIds(projectId, false) || [];

  if (workspaceUserInfo && !canPerformProjectAdminActions) {
    return <NotAuthorizedView section="settings" isProjectView className="h-auto" />;
  }

  const pageTitle = currentProjectDetails?.name
    ? `${currentProjectDetails.name} settings - Time Tracking`
    : "Time Tracking Settings";

  return (
    <SettingsContentWrapper header={<FeaturesTimeTrackingProjectSettingsHeader />}>
      <PageHead title={pageTitle} />
      <section dir="rtl" className="w-full text-start">
        <SettingsHeading
          title="ثبت و ردگیری زمان (Time Tracking)"
          description="پیکربندی ثبت زمان کاری، تایمر زنده تسک‌ها، قوانین هم‌پوشانی و فواصل استراحت برای اعضای این پروژه."
        />

        {isLoading ? (
          <div className="mt-7 text-body-xs-regular text-tertiary">در حال بارگذاری تنظیمات...</div>
        ) : settings ? (
          <div className="mt-7 flex flex-col gap-4">
            {/* 1. Main enable toggle */}
            <SettingsBoxedControlItem
              title="فعال‌سازی قابلیت Time Tracking در پروژه"
              description="با فعال بودن این گزینه، ویجت زمان، تایمر زنده و امکان لاگ زمان روی تمامی تسک‌های این پروژه در دسترس خواهد بود."
              control={
                <Switch
                  size="sm"
                  checked={settings.is_enabled}
                  onCheckedChange={(checked) => handleUpdate({ is_enabled: checked })}
                  aria-label="فعال‌سازی قابلیت Time Tracking در پروژه"
                />
              }
            />

            {settings.is_enabled && (
              <>
                {/* 2. Task overlap & exceptions */}
                <SettingsBoxedControlItem
                  title="هم‌پوشانی تسک‌ها (Task Overlap)"
                  description="آیا یک کاربر مجاز است هم‌زمان روی بیش از یک تسک تایمر فعال داشته باشد؟"
                  control={
                    <Switch
                      size="sm"
                      checked={settings.allow_overlap}
                      onCheckedChange={(checked) => handleUpdate({ allow_overlap: checked })}
                      aria-label="هم‌پوشانی تسک‌ها"
                    />
                  }
                />

                {!settings.allow_overlap && (
                  <div className={SUB_PANEL_CLASSNAME}>
                    <div className="flex flex-col gap-1">
                      <h4 className="text-body-sm-medium text-primary">استثنائات هم‌پوشانی</h4>
                      <p className="text-caption-md-regular text-tertiary">
                        اعضای انتخاب‌شده حتی در صورت ممنوعیت هم‌پوشانی، می‌توانند هم‌زمان روی چند تسک تایم بزنند.
                      </p>
                    </div>
                    <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                      {projectMemberIds.map((memberId) => {
                        const user = getUserDetails(memberId);
                        const isExempt = settings.overlap_allowed_members.includes(memberId);
                        return (
                          <Checkbox
                            key={memberId}
                            label={user?.display_name || user?.email || memberId}
                            stretch="full"
                            checked={isExempt}
                            onCheckedChange={(checked) => {
                              const newMembers = checked
                                ? [...settings.overlap_allowed_members, memberId]
                                : settings.overlap_allowed_members.filter((id) => id !== memberId);
                              handleUpdate({ overlap_allowed_members: newMembers });
                            }}
                          />
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* 3. Break announcements / focus intervals */}
                <SettingsBoxedControlItem
                  title="اعلام زمان‌های استراحت (دوره‌های تمرکز و آنتراکت)"
                  description="ارسال اعلان و هشدار در ویجت شناور کاربر پس از گذشت مدت مشخصی از کار پیوسته."
                  control={
                    <Switch
                      size="sm"
                      checked={settings.breaks_enabled}
                      onCheckedChange={(checked) => handleUpdate({ breaks_enabled: checked })}
                      aria-label="اعلام زمان‌های استراحت"
                    />
                  }
                />

                {settings.breaks_enabled && (
                  <div className={cn(SUB_PANEL_CLASSNAME, "sm:grid sm:grid-cols-2 sm:gap-4")}>
                    <div className="flex flex-col gap-1.5">
                      <label className="text-body-xs-medium text-secondary">مدت زمان تمرکز (دقیقه)</label>
                      <Input
                        size="lg"
                        type="number"
                        min="1"
                        max="180"
                        value={settings.focus_duration_minutes}
                        onChange={(e) =>
                          setSettings({
                            ...settings,
                            focus_duration_minutes: Number(e.target.value) || 15,
                          })
                        }
                        onBlur={() =>
                          handleUpdate({
                            focus_duration_minutes: settings.focus_duration_minutes,
                          })
                        }
                      />
                      <span className="text-caption-md-regular text-tertiary">مثال: هر ۱۵ یا ۲۵ دقیقه تمرکز پیوسته</span>
                    </div>

                    <div className="flex flex-col gap-1.5">
                      <label className="text-body-xs-medium text-secondary">مدت زمان آنتراکت و استراحت (دقیقه)</label>
                      <Input
                        size="lg"
                        type="number"
                        min="1"
                        max="60"
                        value={settings.break_duration_minutes}
                        onChange={(e) =>
                          setSettings({
                            ...settings,
                            break_duration_minutes: Number(e.target.value) || 5,
                          })
                        }
                        onBlur={() =>
                          handleUpdate({
                            break_duration_minutes: settings.break_duration_minutes,
                          })
                        }
                      />
                      <span className="text-caption-md-regular text-tertiary">مثال: ۵ دقیقه استراحت کوتاه</span>
                    </div>
                  </div>
                )}

                {/* 4. Logging permissions */}
                <div className={SUB_PANEL_CLASSNAME}>
                  <div className="flex flex-col gap-1">
                    <h4 className="text-body-sm-medium text-primary">دسترسی و مجوز ثبت زمان روی تسک‌ها</h4>
                    <p className="text-caption-md-regular text-tertiary">
                      تعیین کنید چه افرادی مجاز به استارت تایمر و ثبت لاگ زمان روی تسک‌های این پروژه هستند.
                    </p>
                  </div>

                  <RadioInput
                    name="logging_permission"
                    ariaLabel="دسترسی ثبت زمان"
                    vertical
                    selected={settings.logging_permission}
                    onChange={(value) => handleUpdate({ logging_permission: value as TProjectTimeTrackingSetting["logging_permission"] })}
                    options={[
                      { value: "all_members", label: "تمامی اعضای تیم این پروژه مجاز به ثبت زمان هستند" },
                      { value: "assignee_only", label: "فقط فرد یا افرادی که تسک به آن‌ها محول شده است (Assignee)" },
                      { value: "custom_members", label: "افراد خاصی به همراه فرد اساینی (انتخاب سفارشی اعضا)" },
                    ]}
                  />

                  {settings.logging_permission === "custom_members" && (
                    <div className="grid grid-cols-1 gap-2 border-t border-subtle pt-3 sm:grid-cols-2">
                      {projectMemberIds.map((memberId) => {
                        const user = getUserDetails(memberId);
                        const isAllowed = settings.custom_allowed_members.includes(memberId);
                        return (
                          <Checkbox
                            key={memberId}
                            label={user?.display_name || user?.email || memberId}
                            stretch="full"
                            checked={isAllowed}
                            onCheckedChange={(checked) => {
                              const newMembers = checked
                                ? [...settings.custom_allowed_members, memberId]
                                : settings.custom_allowed_members.filter((id) => id !== memberId);
                              handleUpdate({ custom_allowed_members: newMembers });
                            }}
                          />
                        );
                      })}
                    </div>
                  )}
                </div>

                {/* 5. Default report view */}
                <div className={SUB_PANEL_CLASSNAME}>
                  <div className="flex flex-col gap-1">
                    <h4 className="text-body-sm-medium text-primary">روش نمایش پیش‌فرض گزارش تایم روی تسک‌ها</h4>
                    <p className="text-caption-md-regular text-tertiary">
                      کاربران هنگام باز کردن جزئیات هر تسک، زمان ثبت‌شده را به چه صورتی مشاهده کنند؟ (قابل تغییر توسط کاربر در صفحه تسک)
                    </p>
                  </div>

                  <RadioInput
                    name="default_view"
                    ariaLabel="روش نمایش پیش‌فرض گزارش"
                    vertical
                    selected={settings.default_view}
                    onChange={(value) => handleUpdate({ default_view: value as TTimeTrackingDefaultView })}
                    options={DEFAULT_VIEW_OPTIONS.map((option) => ({
                      value: option.key,
                      label: (
                        <div className="flex flex-col">
                          <span className="text-body-xs-medium text-primary">{option.title}</span>
                          <span className="text-caption-md-regular text-tertiary">{option.description}</span>
                        </div>
                      ),
                    }))}
                  />
                </div>
              </>
            )}
          </div>
        ) : null}
      </section>
    </SettingsContentWrapper>
  );
}

export default observer(FeaturesTimeTrackingSettingsPage);
