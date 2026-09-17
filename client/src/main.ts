import { bootstrapApplication } from '@angular/platform-browser';
import { appConfig } from './app/app.config';
import { AppComponent } from './app/pages/app/app.component';

const revealApp = () => {
  document.documentElement.classList.add('orion-ready');
};

bootstrapApplication(AppComponent, appConfig)
  .then(revealApp)
  .catch((err) => {
    revealApp();
    console.error(err);
  });
