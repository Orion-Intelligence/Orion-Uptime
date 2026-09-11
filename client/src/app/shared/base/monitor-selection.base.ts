import { signal } from '@angular/core';
import { FormGroup } from '@angular/forms';
import { MonitorOverview } from '../model/models';
import { firstInvalidFieldMessage } from '../utils/form.util';

export abstract class MonitorSelectionBase {
  readonly monitors = signal<MonitorOverview[]>([]);
  readonly selectedIds = signal<Set<string>>(new Set());
  readonly error = signal('');

  isSelected(monitorId: string): boolean {
    return this.selectedIds().has(monitorId);
  }

  protected validateForm(form: FormGroup, messages: Map<string, string>): boolean {
    this.error.set('');
    form.markAllAsTouched();
    if (form.invalid) {
      this.error.set(firstInvalidFieldMessage(form, messages));
      return false;
    }
    return true;
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
