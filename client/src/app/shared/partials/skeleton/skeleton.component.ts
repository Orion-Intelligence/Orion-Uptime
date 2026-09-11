import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

export type SkeletonVariant = 'list' | 'table' | 'detail' | 'dashboard' | 'form' | 'status';

@Component({
  selector: 'orion-skeleton',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { role: 'status', 'aria-busy': 'true', 'aria-label': 'Loading', class: 'tw:block' },
  templateUrl: './skeleton.component.html',
})
export class SkeletonComponent {
  protected readonly cards = computed(() => Array.from({ length: this.count() }, (_, i) => i));
  protected readonly tiles = [0, 1, 2, 3];

  readonly variant = input.required<SkeletonVariant>();
  readonly count = input(6);
  readonly summary = input(false);
  readonly header = input(false);
}
