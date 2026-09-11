import { signal } from '@angular/core';
import { MonitorOverview } from '../model/models';

export abstract class MonitorSelectionBase {
  readonly monitors = signal<MonitorOverview[]>([]);
  readonly selectedIds = signal<Set<string>>(new Set());

  isSelected(monitorId: string): boolean {
    return this.selectedIds().has(monitorId);
  }

  toggleMonitor(monitorId: string): void {
    this.selectedIds.update((current) => {
      const selected = new Set(current);
      if (selected.has(monitorId)) {
        selected.delete(monitorId);
      }
      else {
        selected.add(monitorId);
      }
      return selected;
    });
  }
}
