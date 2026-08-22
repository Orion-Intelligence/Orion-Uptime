import { afterNextRender, DOCUMENT, EnvironmentProviders, inject, makeEnvironmentProviders, provideEnvironmentInitializer } from '@angular/core';
import { NavigationEnd, NavigationStart, Router } from '@angular/router';
import { filter, switchMap, take } from 'rxjs';

const ANIMATIONS_READY_CLASS = 'orion-animations-ready';
const NAVIGATED_CLASS = 'orion-navigated';

export function providePageAnimations(): EnvironmentProviders {
  return makeEnvironmentProviders([
    provideEnvironmentInitializer(() => {
      const root = inject(DOCUMENT).documentElement;
      const events = inject(Router).events;
      const initialNavigationEnd = events.pipe(filter((event) => event instanceof NavigationEnd), take(1));
      const firstInAppNavigation = initialNavigationEnd.pipe(switchMap(() => events.pipe(filter((event) => event instanceof NavigationStart), take(1))));
      firstInAppNavigation.subscribe(() => {
        root.classList.add(NAVIGATED_CLASS);
      });
      afterNextRender(() => {
        requestAnimationFrame(() => {
          requestAnimationFrame(() => {
            root.classList.add(ANIMATIONS_READY_CLASS);
          });
        });
      });
    }),
  ]);
}
