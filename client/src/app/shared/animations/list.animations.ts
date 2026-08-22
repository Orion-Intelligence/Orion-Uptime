import { animate, query, stagger, style, transition, trigger } from '@angular/animations';

/**
 * Bind to the list length on the element that wraps a `@for` block.
 * Newly inserted children fade in one after another (first 24 staggered, the rest appear at once).
 * Opacity only: cards, rows and their text/icons never move or scale.
 */
export const listStaggerAnimation = trigger('listStagger', [
  transition('* => *', [
    query(':enter', [
      style({ opacity: 0 }),
      stagger('40ms', animate('260ms ease-out', style({ opacity: 1 }))),
    ], { optional: true, limit: 24 }),
  ]),
]);
