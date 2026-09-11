import { Component, computed, HostListener, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { finalize } from 'rxjs';
import { ApiService } from '../../services/core/api.service';
import { SystemLogEntry, SystemLogPage } from '../../shared/model/models';

interface CalendarDay {
  iso: string;
  label: number;
  inMonth: boolean;
  disabled: boolean;
  isFrom: boolean;
  isTo: boolean;
  inRange: boolean;
}

@Component({
  selector: 'app-log-manager',
  imports: [FormsModule],
  templateUrl: './log-manager.component.html',
})
export class LogManagerComponent {
  private readonly api = inject(ApiService);

  readonly logTypes = ['All', 'warning', 'info', 'error'];
  readonly weekdays = ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su'];
  readonly logs = signal<SystemLogEntry[]>([]);
  readonly loading = signal(false);
  readonly error = signal('');
  readonly page = signal(1);
  readonly limit = signal(200);
  readonly total = signal<number | null>(null);
  readonly hasMore = signal(false);
  readonly sourceProfileName = signal<string | null>(null);
  readonly loaded = signal(false);
  readonly calendarOpen = signal(false);
  readonly rangeFrom = signal('');
  readonly rangeTo = signal('');
  readonly calendarMonth = signal(new Date(new Date().getFullYear(), new Date().getMonth(), 1));
  readonly todayIso = this.toIso(new Date());
  logType = 'All';
  readonly hasRange = computed(() => Boolean(this.rangeFrom() && this.rangeTo()));
  readonly monthLabel = computed(() => this.calendarMonth().toLocaleDateString(undefined, { month: 'long', year: 'numeric' }));
  readonly canGoNextMonth = computed(() => {
    const month = this.calendarMonth();
    const now = new Date();
    return month.getFullYear() < now.getFullYear() || (month.getFullYear() === now.getFullYear() && month.getMonth() < now.getMonth());
  });
  readonly rangeLabel = computed(() => {
    const from = this.rangeFrom();
    const to = this.rangeTo();
    if (!from) {
      return 'Select date range';
    }
    if (!to) {
      return `${this.formatDay(from)} — choose end date`;
    }
    return `${this.formatDay(from)} — ${this.formatDay(to)}`;
  });
  readonly calendarDays = computed<CalendarDay[]>(() => {
    const month = this.calendarMonth();
    const first = new Date(month.getFullYear(), month.getMonth(), 1);
    const offset = (first.getDay() + 6) % 7;
    const from = this.rangeFrom();
    const to = this.rangeTo();
    const days: CalendarDay[] = [];
    for (let index = 0; index < 42; index += 1) {
      const date = new Date(first.getFullYear(), first.getMonth(), 1 - offset + index);
      const iso = this.toIso(date);
      days.push({
        iso,
        label: date.getDate(),
        inMonth: date.getMonth() === month.getMonth(),
        disabled: iso > this.todayIso,
        isFrom: iso === from,
        isTo: iso === to,
        inRange: Boolean(from) && Boolean(to) && iso > from && iso < to,
      });
    }
    return days;
  });

  constructor() {
    this.loadLogs();
  }

  @HostListener('document:click', ['$event'])
  closeCalendarOnOutsideClick(event: MouseEvent): void {
    const target = event.target;
    if (target instanceof Element && !target.closest('.log-date-range')) {
      this.calendarOpen.set(false);
    }
  }

  @HostListener('document:keydown.escape')
  closeCalendar(): void {
    this.calendarOpen.set(false);
  }

  toggleCalendar(): void {
    this.calendarOpen.update((open) => !open);
  }

  previousMonth(): void {
    this.calendarMonth.update((month) => new Date(month.getFullYear(), month.getMonth() - 1, 1));
  }

  nextMonth(): void {
    if (!this.canGoNextMonth()) {
      return;
    }
    this.calendarMonth.update((month) => new Date(month.getFullYear(), month.getMonth() + 1, 1));
  }

  selectDate(day: CalendarDay): void {
    if (day.disabled) {
      return;
    }
    const from = this.rangeFrom();
    const to = this.rangeTo();
    if (!from || to) {
      this.rangeFrom.set(day.iso);
      this.rangeTo.set('');
      return;
    }
    if (day.iso < from) {
      this.rangeFrom.set(day.iso);
      return;
    }
    this.rangeTo.set(day.iso);
    this.calendarOpen.set(false);
    this.applyFilters();
  }

  clearRange(): void {
    if (!this.rangeFrom() && !this.rangeTo()) {
      return;
    }
    this.rangeFrom.set('');
    this.rangeTo.set('');
    this.calendarOpen.set(false);
    this.applyFilters();
  }

  loadLogs(): void {
    this.loading.set(true);
    this.error.set('');
    this.api
      .get<SystemLogPage>(this.buildPath())
      .pipe(finalize(() => {
        this.loading.set(false);
        this.loaded.set(true);
      }))
      .subscribe({
        next: (response) => {
          const data = response.data;
          this.logs.set(data?.logs ?? []);
          this.page.set(data?.page ?? 1);
          this.limit.set(data?.limit ?? this.limit());
          this.total.set(data?.total ?? null);
          this.hasMore.set(Boolean(data?.has_more));
          this.sourceProfileName.set(data?.source_profile_name ?? null);
        },
        error: (error: unknown) => {
          this.logs.set([]);
          this.hasMore.set(false);
          this.total.set(null);
          this.error.set(ApiService.errorMessage(error));
        },
      });
  }

  applyFilters(): void {
    this.page.set(1);
    this.loadLogs();
  }

  previousPage(): void {
    if (this.page() <= 1) {
      return;
    }
    this.page.update((value) => value - 1);
    this.loadLogs();
  }

  nextPage(): void {
    if (!this.hasMore()) {
      return;
    }
    this.page.update((value) => value + 1);
    this.loadLogs();
  }

  typeClass(type: string): string {
    const value = type.toLowerCase();
    if (value.includes('error') || value.includes('critical') || value.includes('fatal')) {
      return 'error';
    }
    if (value.includes('warn')) {
      return 'warning';
    }
    if (value.includes('info') || value.includes('debug')) {
      return 'info';
    }
    return 'unknown';
  }

  typeLabel(type: string): string {
    return type.toLowerCase() || 'unknown';
  }

  private formatDay(iso: string): string {
    const [year, month, day] = iso.split('-').map(Number);
    return new Date(year, month - 1, day).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
  }

  private toIso(date: Date): string {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  }

  private buildPath(): string {
    const params = new URLSearchParams();
    params.set('page', String(this.page()));
    params.set('limit', String(this.limit()));
    if (this.logType && this.logType !== 'All') {
      params.set('log_type', this.logType.toUpperCase());
    }
    if (this.rangeFrom()) {
      params.set('date_from', this.rangeFrom());
    }
    if (this.rangeTo()) {
      params.set('date_to', this.rangeTo());
    }
    return `/system-logs?${params.toString()}`;
  }
}
