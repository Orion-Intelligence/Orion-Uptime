import { Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router } from '@angular/router';
import { finalize } from 'rxjs';
import { ApiService } from '../../services/core/api.service';
import { CreateUserRequest, UserResponse } from '../../shared/model/models';

@Component({
  selector: 'app-register-user-page',
  imports: [ReactiveFormsModule],
  templateUrl: './register-user.component.html',
})
export class RegisterUserComponent {
  private readonly fb = inject(FormBuilder);
  private readonly api = inject(ApiService);
  private readonly router = inject(Router);

  readonly loading = signal(false);
  readonly error = signal('');
  readonly form = this.fb.nonNullable.group({
    username: ['', [Validators.required, Validators.minLength(3), Validators.maxLength(50)]],
    password: ['', [Validators.required, Validators.minLength(8)]],
  });

  submit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      this.error.set('Username must be 3–50 characters and the password at least 8 characters.');
      return;
    }
    this.loading.set(true);
    this.error.set('');
    const request: CreateUserRequest = this.form.getRawValue();
    this.api
      .post<UserResponse, CreateUserRequest>('/users/create', request)
      .pipe(finalize(() => {
        this.loading.set(false); 
      }))
      .subscribe({
        next: (response) => {
          void this.router.navigateByUrl('/users', {
            state: {
              message: `${response.data.username} was registered as a viewer.`,
            },
          });
        },
        error: (error: unknown) => {
          this.error.set(ApiService.errorMessage(error)); 
        },
      });
  }
}
