import { animate, style, transition, trigger } from '@angular/animations';

/** Notices, alerts, loading bars and summary panels: fade in when shown, fade out when removed. */
export const fadeInOutAnimation = trigger('fadeInOut', [
  transition(':enter', [
    style({ opacity: 0 }),
    animate('220ms ease-out', style({ opacity: 1 })),
  ]),
  transition(':leave', [
    animate('160ms ease-in', style({ opacity: 0 })),
  ]),
]);

/** Content blocks that swap with a sibling (inline forms, chart fallbacks): fade in only, so the outgoing block never overlaps the incoming one. */
export const fadeInAnimation = trigger('fadeIn', [
  transition(':enter', [
    style({ opacity: 0 }),
    animate('240ms ease-out', style({ opacity: 1 })),
  ]),
]);

/** Bound to a value (chart range, selected tab): every change re-fades the block's content in place. */
export const crossFadeAnimation = trigger('crossFade', [
  transition('* => *', [
    style({ opacity: 0.35 }),
    animate('260ms ease-out', style({ opacity: 1 })),
  ]),
]);
