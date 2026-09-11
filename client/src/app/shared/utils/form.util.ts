import { FormGroup } from '@angular/forms';

export function firstInvalidFieldMessage(form: FormGroup, messages: Map<string, string>): string {
  const invalid = Object.keys(form.controls).find((key) => form.get(key)?.invalid);
  return (invalid === undefined ? undefined : messages.get(invalid)) ?? 'Check the highlighted fields.';
}
