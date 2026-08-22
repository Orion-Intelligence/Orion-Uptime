import { animate, style, transition, trigger } from '@angular/animations';

export const fadeInOutAnimation = trigger('fadeInOut', [
  transition(':enter', [
    style({ opacity: 0 }),
    animate('220ms ease-out', style({ opacity: 1 })),
  ]),
  transition(':leave', [
    animate('160ms ease-in', style({ opacity: 0 })),
  ]),
]);

export const fadeInAnimation = trigger('fadeIn', [
  transition(':enter', [
    style({ opacity: 0 }),
    animate('240ms ease-out', style({ opacity: 1 })),
  ]),
]);

export const crossFadeAnimation = trigger('crossFade', [
  transition('* => *', [
    style({ opacity: 0.35 }),
    animate('260ms ease-out', style({ opacity: 1 })),
  ]),
]);
