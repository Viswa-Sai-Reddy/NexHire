import { api } from "@/lib/axios";
import type { TaskQueueResponse } from "@/modules/tasks/types";

export async function getMyTasks(): Promise<TaskQueueResponse> {
  const { data } = await api.get<TaskQueueResponse>("/tasks/mine");
  return data;
}

export async function completeAdProvisioning(internId: string): Promise<void> {
  await api.post("/tasks/ad-provision/complete", { intern_id: internId });
}

export async function completeBadgeAccess(
  internId: string,
  badgeReference: string,
): Promise<void> {
  await api.post("/tasks/badge-access/complete", {
    intern_id: internId,
    badge_reference: badgeReference,
  });
}
