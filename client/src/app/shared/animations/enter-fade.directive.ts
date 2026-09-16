import { afterNextRender, Directive, ElementRef, inject } from '@angular/core';

@Directive({
  selector: '[orionEnter]',
})
export class EnterFadeDirective {
  constructor() {
    const element = inject(ElementRef<HTMLElement>).nativeElement;
    element.classList.add('orion-enter');
    afterNextRender(() => {
      requestAnimationFrame(() => element.classList.add('orion-enter-in'));
    });
  }
}
