import { DOCUMENT } from '@angular/common';
import { animate, style, transition, trigger } from '@angular/animations';
import { afterNextRender, EnvironmentProviders, inject, makeEnvironmentProviders, provideEnvironmentInitializer } from '@angular/core';
import { provideAnimations } from '@angular/platform-browser/animations';
import { NavigationEnd, NavigationStart, Router } from '@angular/router';
import { filter, switchMap, take } from 'rxjs';

const ANIMATIONS_READY_CLASS = 'orion-animations-ready';

let navigatedSinceLoad = false;

export const pageEnterAnimation = trigger('pageEnter', [
  transition((fromState, toState) => fromState === 'void' && toState !== 'void' && navigatedSinceLoad, [
    style({ opacity: 0 }),
    animate('320ms ease-out', style({ opacity: 1 })),
  ]),
]);

export function providePageAnimations(): EnvironmentProviders {
  return makeEnvironmentProviders([
    provideAnimations(),
    provideEnvironmentInitializer(() => {
      const events = inject(Router).events;
      const initialNavigationEnd = events.pipe(filter((event) => event instanceof NavigationEnd), take(1));
      const firstInAppNavigation = initialNavigationEnd.pipe(switchMap(() => events.pipe(filter((event) => event instanceof NavigationStart), take(1))));
      firstInAppNavigation.subscribe(() => {
        navigatedSinceLoad = true;
      });

      const root = inject(DOCUMENT).documentElement;
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
