import { PublicUptimeStatus } from '../model/models';

export function buildUptimeWindows(uptime: PublicUptimeStatus): Array<{ label: string; value: number | null }> {
  return [
    { label: 'Last 24 hours', value: uptime.last_24_hours },
    { label: 'Last 7 days', value: uptime.last_7_days },
    { label: 'Last 30 days', value: uptime.last_30_days },
    { label: 'Last 90 days', value: uptime.last_90_days },
  ];
}
