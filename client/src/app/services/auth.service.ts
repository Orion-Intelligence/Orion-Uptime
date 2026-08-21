import { inject, Injectable, signal } from '@angular/core';
import { Observable, switchMap, tap } from 'rxjs';
import { ApiService } from './api.service';
import { CurrentUser, LoginRequest } from '../models/models';

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
      const subscription = this.api.get<CurrentUser>('/auth/me').subscribe({
        next: (response) => {
          this.user.set(response.data);
          subscriber.next(response.data);
          subscriber.complete();
        },
        error: (error: unknown) => {
          this.user.set(null);
          subscriber.error(error);
        },
      });
      return () => subscription.unsubscribe();
    });
  }

  logout(): Observable<unknown> {
    return this.api.post<null>('/auth/logout', {}).pipe(tap(() => this.user.set(null)));
  }
}
