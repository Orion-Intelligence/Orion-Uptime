import { Component, input, output } from '@angular/core';

@Component({
  selector: 'app-delete-confirmation-dialog',
  templateUrl: './delete-confirmation-dialog.component.html',
})
export class DeleteConfirmationDialogComponent {
  readonly message = input.required<string>();
  readonly deleting = input(false);
  readonly confirmed = output();
  readonly cancelled = output();
}
