import { DestroyRef, inject, Injectable, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Observable, map, shareReplay, tap } from 'rxjs';
import { ApiService } from '../core/api.service';
import { RealtimeService } from './realtime.service';
import { ResourceType } from '../../shared/model/models';

@Injectable({ providedIn: 'root' })
export class ResourceService {
  private readonly api = inject(ApiService);
  private readonly realtime = inject(RealtimeService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly endpoints: Record<ResourceType, string> = { HTTP: '/HTTP_monitors/list_all', API: '/API_monitors/list_all', ping: '/ping-monitors/list_all', heartbeat: '/heartbeat-monitors/list_all', orion_script: '/orion-script-monitors/list_all', auth_profiles: '/auth-profiles/list_all', users: '/users/list', status_pages: '/status-pages', slack_integrations: '/integrations/slack', email_integrations: '/integrations/email', };
  private readonly cache = new Map<ResourceType, unknown[]>();
  private readonly inflight = new Map<ResourceType, Observable<unknown[]>>();
  private readonly staleTypes = signal<ResourceType[]>([]);

  readonly changes = this.staleTypes.asReadonly();

  constructor() {
    this.realtime.resourceChanges$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((invalidation) => {
      invalidation.types.forEach((type) => {
        this.cache.delete(type);
        this.inflight.delete(type);
      });
      this.staleTypes.set(invalidation.types);
    });
    this.realtime.resets$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => {
      this.clear();
    });
  }

  list<T>(type: ResourceType, force = false): Observable<T[]> {
    if (!force) {
      const cached = this.cache.get(type);
      if (cached) {
        return new Observable<T[]>((subscriber) => {
          subscriber.next(cached as T[]);
          subscriber.complete();
        });
      }
      const pending = this.inflight.get(type);
      if (pending) {
        return pending as Observable<T[]>;
      }
    }

    const request = this.api.get<T[]>(this.endpoints[type]).pipe(map((response) => response.data ?? []),
      tap((records) => {
        this.cache.set(type, records);
        this.inflight.delete(type);
      }),
      shareReplay({ bufferSize: 1, refCount: false }),);
    this.inflight.set(type, request as Observable<unknown[]>);
    return request;
  }

  invalidate(type: ResourceType): void {
    this.cache.delete(type);
    this.inflight.delete(type);
  }

  clear(): void {
    this.cache.clear();
    this.inflight.clear();
  }
}
