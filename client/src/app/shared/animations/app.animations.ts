import { DOCUMENT } from '@angular/common';
import { animate, style, transition, trigger } from '@angular/animations';
import { afterNextRender, EnvironmentProviders, inject, makeEnvironmentProviders, provideEnvironmentInitializer } from '@angular/core';
import { provideAnimations } from '@angular/platform-browser/animations';
import { NavigationEnd, NavigationStart, Router } from '@angular/router';
import { filter, switchMap, take } from 'rxjs';

/** Added to `<html>` once the first frame has been painted; `theme.transitions.css` keys the document-level colour transitions on it. */
const ANIMATIONS_READY_CLASS = 'orion-animations-ready';

/**
 * Flips to true when the first navigation *after* the initial load starts, i.e. the
 * first in-app route change. Until then `pageEnter` stays inert, so a reload or a
 * direct link (including one the auth guard redirects) shows the page immediately
 * and only the component-level animations (lists, panels, popups) run.
 */
let navigatedSinceLoad = false;

/**
 * Fades a routed page (or the application shell) in when it is created by an
 * in-app navigation. Opacity only: nothing inside the page moves or scales.
 */
export const pageEnterAnimation = trigger('pageEnter', [
  transition((fromState, toState) => fromState === 'void' && toState !== 'void' && navigatedSinceLoad, [
    style({ opacity: 0 }),
    animate('320ms ease-out', style({ opacity: 1 })),
  ]),
]);

/** Registers the animation engine, the page-enter gating and the document ready flag. Load once from `app.config.ts`. */
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
          requestAnimationFrame(() => root.classList.add(ANIMATIONS_READY_CLASS));
        });
      });
    }),
  ]);
}
