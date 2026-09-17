import { inject, Injectable, signal } from '@angular/core';
import { Observable, switchMap, tap } from 'rxjs';
import { ApiService } from '../core/api.service';
import { CurrentUser, LoginRequest } from '../../shared/model/models';

const SIGNED_IN_STORAGE_KEY = 'orion-uptime-signed-in';

const rememberSession = (signedIn: boolean): void => {
  try {
    if (signedIn) {
      window.localStorage.setItem(SIGNED_IN_STORAGE_KEY, '1');
      return;
    }
    window.localStorage.removeItem(SIGNED_IN_STORAGE_KEY);
  }
  catch {
    return;
  }
};

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly api = inject(ApiService);

  readonly user = signal<CurrentUser | null>(null);

  login(credentials: LoginRequest): Observable<CurrentUser> {
    return this.api
      .post<null, LoginRequest>('/auth/login', credentials)
      .pipe(switchMap(() => this.loadCurrentUser()));
  }

  loadCurrentUser(): Observable<CurrentUser> {
    return new Observable((subscriber) => {
      const subscription = this.api.get<CurrentUser | null>('/auth/session').subscribe({
        next: (response) => {
          this.user.set(response.data);
          rememberSession(response.data !== null);
          if (response.data === null) {
            subscriber.error(new Error('No active session.'));
            return;
          }
          subscriber.next(response.data);
          subscriber.complete();
        },
        error: (error: unknown) => {
          this.user.set(null);
          rememberSession(false);
          subscriber.error(error);
        },
      });
      return () => {
        subscription.unsubscribe(); 
      };
    });
  }

  logout(): Observable<unknown> {
    return this.api.post<null>('/auth/logout', {}).pipe(tap(() => {
      this.user.set(null);
      rememberSession(false);
    }));
  }
}
