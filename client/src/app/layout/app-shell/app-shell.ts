import { NgOptimizedImage } from '@angular/common';
import { Component, DestroyRef, HostListener, inject, signal } from '@angular/core';
import { Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { finalize } from 'rxjs';
import { AuthService } from '../../services/auth.service';
import { RealtimeService } from '../../services/realtime.service';
import { ThemeService } from '../../services/theme.service';
import { overlayAnimation, pageEnterAnimation, popupAnimation } from '../../shared/animations';

@Component({
  selector: 'app-shell',
  imports: [NgOptimizedImage, RouterLink, RouterLinkActive, RouterOutlet],
  templateUrl: './app-shell.html',
  animations: [overlayAnimation, pageEnterAnimation, popupAnimation],
})
export class AppShell {
  private readonly realtime = inject(RealtimeService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly router = inject(Router);

  readonly auth = inject(AuthService);
  readonly theme = inject(ThemeService);
  readonly menuOpen = signal(false);
  readonly sidebarCollapsed = signal(false);
  readonly profileOpen = signal(false);
  readonly loggingOut = signal(false);

  constructor() {
    const storedSidebar = window.localStorage.getItem('orion-uptime-sidebar');
    this.sidebarCollapsed.set(storedSidebar === 'collapsed');
    this.realtime.connect();
    this.destroyRef.onDestroy(() => this.realtime.disconnect());
  }

  closeMenu(): void {
    this.menuOpen.set(false);
  }

  breadcrumbSection(): string {
    return this.router.url.startsWith('/status-pages') ||
      this.router.url.startsWith('/auth-profiles') ||
      this.router.url.startsWith('/users')
      ? 'Management'
      : 'Operations';
  }

  breadcrumbPage(): string {
    const path = this.router.url.split('?')[0];
    if (path === '/dashboard') {
      return 'Homepage';
    }
    if (path.startsWith('/monitors/http/new')) {
      return 'New HTTP monitor';
    }
    if (path.startsWith('/monitors/api/new')) {
      return 'New API monitor';
    }
    if (path.startsWith('/monitors/ping/new')) {
      return 'New Ping monitor';
    }
    if (path.startsWith('/monitors/heartbeat/new')) {
      return 'New Heartbeat monitor';
    }
    if (/^\/monitors\/[^/]+\/[^/]+$/.test(path)) {
      return 'Monitor details';
    }
    if (path.startsWith('/monitors/http')) {
      return 'HTTP monitors';
    }
    if (path.startsWith('/monitors/api')) {
      return 'API monitors';
    }
    if (path.startsWith('/monitors/ping')) {
      return 'Ping monitors';
    }
    if (path.startsWith('/monitors/heartbeat')) {
      return 'Heartbeat monitors';
    }
    if (path === '/status-pages/new') {
      return 'New status page';
    }
    if (path.includes('/status-pages/') && path.endsWith('/edit')) {
      return 'Edit status page';
    }
    if (path.startsWith('/status-pages')) {
      return 'Status pages';
    }
    if (path === '/auth-profiles/new') {
      return 'New auth profile';
    }
    if (path.startsWith('/auth-profiles')) {
      return 'Auth profiles';
    }
    if (path === '/users/new') {
      return 'Register user';
    }
    if (path.startsWith('/users')) {
      return 'Users';
    }
    return 'Uptime monitoring';
  }

  toggleSidebar(): void {
    this.sidebarCollapsed.update((collapsed) => !collapsed);
    window.localStorage.setItem('orion-uptime-sidebar',
      this.sidebarCollapsed() ? 'collapsed' : 'expanded',);
  }

  toggleTheme(): void {
    this.theme.toggle();
  }

  @HostListener('document:click', ['$event'])
  closeProfileOnOutsideClick(event: MouseEvent): void {
    const target = event.target;
    if (target instanceof Element && !target.closest('.profile-menu')) {
      this.profileOpen.set(false);
    }
  }

  @HostListener('document:keydown.escape')
  closeOverlays(): void {
    this.profileOpen.set(false);
    this.menuOpen.set(false);
  }

  logout(): void {
    this.loggingOut.set(true);
    this.auth
      .logout()
      .pipe(finalize(() => this.loggingOut.set(false)))
      .subscribe({
        next: () => {
          this.realtime.disconnect();
          void this.router.navigate(['/login']);
        },
        error: () => {
          this.realtime.disconnect();
          this.auth.user.set(null);
          void this.router.navigate(['/login']);
        },
      });
  }
}
