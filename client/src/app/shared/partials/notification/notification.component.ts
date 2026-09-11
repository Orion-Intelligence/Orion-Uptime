import { ChangeDetectionStrategy, Component, input } from '@angular/core';

@Component({
  selector: 'app-notification',
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './notification.component.html',
})
export class NotificationComponent {
  readonly message = input<string>('');
  readonly leaving = input(false);
}
