import { request } from './client';
import type { EduLesson } from './types';

/** Moments kept waiting (one bubble is shown; the dock badge and Buddy list the rest). */
export const MAX_EDU_BUBBLES = 3;

export function fetchLesson(campaignId: string, momentId: string): Promise<EduLesson> {
  return request<EduLesson>('POST', `/campaigns/${campaignId}/edu/${momentId}/lesson`);
}

export function dismissMoment(campaignId: string, momentId: string): Promise<void> {
  return request<void>('POST', `/campaigns/${campaignId}/edu/${momentId}/dismiss`);
}
