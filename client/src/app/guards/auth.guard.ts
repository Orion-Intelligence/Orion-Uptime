import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { catchError, map, of } from 'rxjs';
import { AuthService } from '../services/auth.service';

export const authGuard: CanActivateFn = () => {
  const auth = inject(AuthService);
  const router = inject(Router);

  if (auth.user()) {
    return true;
  }

  return auth.loadCurrentUser().pipe(map(() => true),
    catchError(() => of(router.createUrlTree(['/login']))),);
};

export const adminGuard: CanActivateFn = () => {
  const auth = inject(AuthService);
  const router = inject(Router);
  return auth.user()?.role === 'admin' ? true : router.createUrlTree(['/dashboard']);
};
