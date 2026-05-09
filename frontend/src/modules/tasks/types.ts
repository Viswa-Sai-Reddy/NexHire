/**
 * Mirrors `backend/app/modules/access/router.py`.
 */

export interface TaskQueueEntry {
  id: string;
  task_type: string;
  intern_id: string | null;
  referral_id: string | null;
  sla_deadline: string;
  status: string;
  ai_routing_reason: string | null;
  created_at: string;
}

export interface TaskQueueResponse {
  items: TaskQueueEntry[];
}
