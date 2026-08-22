import { animate, style, transition, trigger } from '@angular/animations';

export const popupAnimation = trigger('popup', [
  transition(':enter', [
    style({ opacity: 0 }),
    animate('160ms ease-out', style({ opacity: 1 })),
  ]),
  transition(':leave', [
    animate('120ms ease-in', style({ opacity: 0 })),
  ]),
]);

export const overlayAnimation = trigger('overlay', [
  transition(':enter', [
    style({ opacity: 0 }),
    animate('200ms ease-out', style({ opacity: 1 })),
  ]),
  transition(':leave', [
    animate('160ms ease-in', style({ opacity: 0 })),
  ]),
]);
