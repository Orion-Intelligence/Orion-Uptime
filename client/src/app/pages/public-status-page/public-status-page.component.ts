import { DatePipe, DecimalPipe, NgOptimizedImage, isPlatformBrowser } from '@angular/common';
import { Component, computed, effect, inject, PLATFORM_ID, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { PublicStreamPageBase } from '../../shared/base/public-stream.base';
import { ApiService } from '../../services/core/api.service';
import { buildUptimeWindows } from '../../shared/utils/uptime.util';
import { DailyUptime, PublicOrionFeeder, PublicOrionScript, PublicOrionScriptUptime, PublicStatusMonitor, PublicStatusPage } from '../../shared/model/models';

const SOCIAL_SECTION = 'social';

const MONITOR_GROUPS = [
  { type: 'HTTP', label: 'HTTP monitors' },
  { type: 'API', label: 'API monitors' },
  { type: 'ping', label: 'Ping monitors' },
  { type: 'heartbeat', label: 'Heartbeat monitors' },
] as const;

interface MonitorGroup {
  type: string;
  label: string;
  monitors: PublicStatusMonitor[];
}

interface FeederTab {
  key: string;
  label: string;
  feeders: PublicOrionFeeder[];
}

interface OrionSection {
  script: PublicOrionScript;
  tabs: FeederTab[];
}

@Component({
  selector: 'app-public-status-page',
  imports: [DatePipe, DecimalPipe, NgOptimizedImage, RouterLink],
  templateUrl: './public-status-page.component.html',
})
export class PublicStatusPageComponent extends PublicStreamPageBase {
  private readonly platformId = inject(PLATFORM_ID);
  private readonly api = inject(ApiService);
  private readonly slug = inject(ActivatedRoute).snapshot.paramMap.get('slug') ?? '';
  private readonly feederBars = signal<Record<string, Record<string, DailyUptime[]>>>({});
  private readonly requestedTabs = new Set<string>();

  readonly page = signal<PublicStatusPage | null>(null);
  readonly monitorGroups = computed<MonitorGroup[]>(() => {
    const monitors = this.page()?.monitors ?? [];
    return MONITOR_GROUPS
      .map((group) => ({
        ...group,
        monitors: monitors.filter((monitor) => monitor.monitor_type === group.type),
      }))
      .filter((group) => group.monitors.length > 0);
  });
  readonly selectedTabs = signal<Partial<Record<string, string>>>({});
  readonly orionSections = computed<OrionSection[]>(() =>
    (this.page()?.orion_scripts ?? []).map((script) => ({ script, tabs: this.feederTabs(script.feeders) })),);

  constructor() {
    super();
    if (isPlatformBrowser(this.platformId)) {
      this.clockTimer = setInterval(() => {
        this.now.set(Date.now());
      }, 1000);
      this.connect();
      effect(() => {
        for (const section of this.orionSections()) {
          const tab = this.activeTab(section);
          if (tab) {
            this.loadTabUptime(section.script.id, tab.key);
          }
        }
      });
    }
  }

  activeTab(section: OrionSection): FeederTab | undefined {
    const selected = this.selectedTabs()[section.script.id];
    return section.tabs.find((tab) => tab.key === selected) ?? section.tabs[0];
  }

  selectTab(scriptId: string, tabKey: string): void {
    this.selectedTabs.update((tabs) => ({ ...tabs, [scriptId]: tabKey }));
  }

  barsReady(scriptId: string, tabKey: string): boolean {
    return this.tabCacheKey(scriptId, tabKey) in this.feederBars();
  }

  feederDaily(scriptId: string, tabKey: string, feederKey: string): DailyUptime[] {
    return this.feederBars()[this.tabCacheKey(scriptId, tabKey)]?.[feederKey] ?? [];
  }

  private tabCacheKey(scriptId: string, tabKey: string): string {
    return scriptId + '::' + tabKey;
  }

  private loadTabUptime(scriptId: string, tabKey: string): void {
    const cacheKey = this.tabCacheKey(scriptId, tabKey);
    if (this.requestedTabs.has(cacheKey)) {
      return;
    }
    this.requestedTabs.add(cacheKey);
    const path = `/status-pages/public/${encodeURIComponent(this.slug)}/orion-scripts/${encodeURIComponent(scriptId)}/uptime?section=${encodeURIComponent(tabKey)}`;
    this.api.get<PublicOrionScriptUptime>(path).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (response) => {
        const bars: Record<string, DailyUptime[]> = {};
        for (const feeder of response.data?.feeders ?? []) {
          bars[feeder.key] = feeder.daily_uptime;
        }
        this.feederBars.update((current) => ({ ...current, [cacheKey]: bars }));
      },
      error: () => {
        this.requestedTabs.delete(cacheKey);
      },
    });
  }

  feederName(feeder: PublicOrionFeeder): string {
    return /^https?:\/\//i.test(feeder.name) ? feeder.name : feeder.name.replace(/^_+/, '').replace(/\.py$/i, '');
  }

  private feederTabs(feeders: PublicOrionFeeder[]): FeederTab[] {
    const tabs = new Map<string, FeederTab>();
    for (const feeder of feeders) {
      const key = feeder.section ?? feeder.rule_key ?? '';
      const tab = tabs.get(key) ?? { key, label: this.tabLabel(key), feeders: [] };
      tab.feeders.push(feeder);
      tabs.set(key, tab);
    }
    return [...tabs.values()].sort((a, b) => Number(a.key === SOCIAL_SECTION) - Number(b.key === SOCIAL_SECTION) || a.label.localeCompare(b.label));
  }

  private tabLabel(key: string): string {
    if (key === SOCIAL_SECTION) {
      return 'Social Media';
    }
    const label = key.replace(/_/g, ' ').trim();
    return label ? label.charAt(0).toUpperCase() + label.slice(1) : 'Other';
  }

  nextUpdateIn(page: PublicStatusPage): number {
    const interval = Math.max(1, page.refresh_interval_seconds);
    const elapsed = Math.max(0, Math.floor((this.now() - Date.parse(page.generated_at)) / 1000));
    return Math.max(0, interval - elapsed);
  }

  uptimeWindows(page: PublicStatusPage): Array<{ label: string; value: number | null }> {
    return buildUptimeWindows(page.uptime_status);
  }

  protected connect(): void {
    const source = new EventSource(`/api/status-pages/public/${encodeURIComponent(this.slug)}/events`,);
    this.source = source;
    source.onopen = () => {
      this.error.set('');
      this.resetReconnectDelay();
    };
    source.addEventListener('snapshot', (event) => {
      try {
        this.page.set(JSON.parse((event as MessageEvent<string>).data) as PublicStatusPage);
        this.loading.set(false);
        this.error.set('');
      }
      catch {
        this.error.set('The latest status update could not be displayed.');
      }
    });
    source.addEventListener('deleted', () => {
      this.source?.close();
      this.clearReconnect();
      this.loading.set(false);
      this.page.set(null);
      this.error.set('This status page is no longer available.');
    });
    source.onerror = () => {
      if (!this.page()) {
        this.loading.set(false);
        this.error.set('This status page is unavailable.');
      }
      if (source.readyState === EventSource.CLOSED) {
        this.scheduleReconnect();
      }
    };
  }
}
