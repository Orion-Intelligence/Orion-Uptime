import { DestroyRef, inject, signal } from '@angular/core';
import { DailyUptime, PublicStatusMonitor } from '../model/models';
import { RECONNECT_MAX_DELAY_MS, RECONNECT_START_DELAY_MS } from '../constants/ui.constants';

export abstract class PublicStreamPageBase {
  private reconnectTimer: ReturnType<typeof setTimeout> | undefined;
  private reconnectDelayMs = RECONNECT_START_DELAY_MS;

  protected readonly destroyRef = inject(DestroyRef);
  protected source: EventSource | undefined;
  protected clockTimer: ReturnType<typeof setInterval> | undefined;

  readonly loading = signal(true);
  readonly connected = signal(false);
  readonly error = signal('');
  readonly now = signal(Date.now());

  protected constructor() {
    this.destroyRef.onDestroy(() => {
      this.source?.close();
      this.clearReconnect();
      if (this.clockTimer) {
        clearInterval(this.clockTimer);
      }
    });
  }

  monitorStatus(monitor: Pick<PublicStatusMonitor, 'is_active' | 'status'>): string {
    return monitor.is_active ? monitor.status : 'paused';
  }

  dayClass(day: DailyUptime): string {
    if (day.uptime_percentage === null) {
      return 'no-data';
    }
    if (day.uptime_percentage >= 100) {
      return 'up';
    }
    if (day.uptime_percentage >= 90) {
      return 'good';
    }
    if (day.uptime_percentage >= 75) {
      return 'minor';
    }
    if (day.uptime_percentage >= 50) {
      return 'major';
    }
    if (day.uptime_percentage >= 25) {
      return 'severe';
    }
    return 'down';
  }

  dayLabel(day: DailyUptime): string {
    const percentage =
      day.uptime_percentage === null ? 'No data' : `${day.uptime_percentage.toFixed(2)}% uptime`;
    return `${day.date} · ${percentage}`;
  }

  protected abstract connect(): void;

  protected resetReconnectDelay(): void {
    this.reconnectDelayMs = RECONNECT_START_DELAY_MS;
  }

  protected scheduleReconnect(): void {
    if (this.reconnectTimer) {
      return;
    }
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = undefined;
      this.source?.close();
      this.connect();
    }, this.reconnectDelayMs);
    this.reconnectDelayMs = Math.min(this.reconnectDelayMs * 2, RECONNECT_MAX_DELAY_MS);
  }

  protected clearReconnect(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = undefined;
    }
  }
}
