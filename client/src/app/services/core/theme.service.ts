import { isPlatformBrowser } from '@angular/common';
import { DOCUMENT, inject, Injectable, PLATFORM_ID, signal } from '@angular/core';

type AppTheme = 'dark' | 'light';

const THEME_STORAGE_KEY = 'orion-uptime-theme';

@Injectable({ providedIn: 'root' })
export class ThemeService {
  private readonly document = inject(DOCUMENT);
  private readonly platformId = inject(PLATFORM_ID);

  readonly theme = signal<AppTheme>(this.storedTheme() ?? 'light');

  constructor() {
    this.applyTheme();
  }

  toggle(): void {
    this.theme.update((theme) => (theme === 'dark' ? 'light' : 'dark'));
    this.persistTheme();
    this.applyTheme();
  }

  private storedTheme(): AppTheme | null {
    if (!isPlatformBrowser(this.platformId)) {
      return null;
    }
    try {
      const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
      return stored === 'dark' || stored === 'light' ? stored : null;
    }
    catch {
      return null;
    }
  }

  private persistTheme(): void {
    if (!isPlatformBrowser(this.platformId)) {
      return;
    }
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, this.theme());
    }
    catch {
      return;
    }
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
