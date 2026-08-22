import { animate, query, stagger, style, transition, trigger } from '@angular/animations';

export const listStaggerAnimation = trigger('listStagger', [
  transition('* => *', [
    query(':enter', [
      style({ opacity: 0 }),
      stagger('40ms', animate('260ms ease-out', style({ opacity: 1 }))),
    ], { optional: true, limit: 24 }),
  ]),
]);
