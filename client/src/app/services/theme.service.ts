import { DOCUMENT, isPlatformBrowser } from '@angular/common';
import { inject, Injectable, PLATFORM_ID, signal } from '@angular/core';

export type AppTheme = 'dark' | 'light';

@Injectable({ providedIn: 'root' })
export class ThemeService {
  private readonly document = inject(DOCUMENT);
  private readonly platformId = inject(PLATFORM_ID);

  readonly theme = signal<AppTheme>('dark');

  constructor() {
    if (isPlatformBrowser(this.platformId)) {
      const stored = window.localStorage.getItem('orion-uptime-theme');
      this.theme.set(stored === 'light' ? 'light' : 'dark');
    }
    this.applyTheme();
  }

  toggle(): void {
    this.theme.update((theme) => (theme === 'dark' ? 'light' : 'dark'));
    if (isPlatformBrowser(this.platformId)) {
      window.localStorage.setItem('orion-uptime-theme', this.theme());
    }
    this.applyTheme();
  }

  private applyTheme(): void {
    const root = this.document.documentElement;
    const body = this.document.body;
    root.classList.toggle('light-theme', this.theme() === 'light');
    root.classList.toggle('dark-theme', this.theme() === 'dark');
    body.classList.toggle('light-theme', this.theme() === 'light');
    body.classList.toggle('dark-theme', this.theme() === 'dark');
  }
}
