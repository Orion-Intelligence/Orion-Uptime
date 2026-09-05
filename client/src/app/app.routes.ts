import { Routes } from '@angular/router';
import { adminGuard, authGuard } from './shared/guards/auth.guard';
const loadAppShellComponent = () => import('./shared/partials/app-shell/app-shell.component').then((m) => m.AppShellComponent);
const loadDashboardComponent = () => import('./pages/dashboard/dashboard.component').then((m) => m.DashboardComponent);
const loadLoginComponent = () => import('./pages/login/login.component').then((m) => m.LoginComponent);
const loadAddMonitorComponent = () => import('./pages/add-monitor/add-monitor.component').then((m) => m.AddMonitorComponent);
const loadMonitorDetailComponent = () => import('./pages/monitor-detail/monitor-detail.component').then((m) => m.MonitorDetailComponent);
const loadRegisterUserComponent = () => import('./pages/register-user/register-user.component').then((m) => m.RegisterUserComponent);
const loadMonitorListComponent = () => import('./pages/monitor-list/monitor-list.component').then((m) => m.MonitorListComponent);
const loadUserListComponent = () => import('./pages/user-list/user-list.component').then((m) => m.UserListComponent);
const loadStatusPageListComponent = () => import('./pages/status-page-list/status-page-list.component').then((m) => m.StatusPageListComponent);
const loadStatusPageEditorComponent = () => import('./pages/status-page-editor/status-page-editor.component').then((m) => m.StatusPageEditorComponent);
const loadIntegrationListComponent = () => import('./pages/integration-list/integration-list.component').then((m) => m.IntegrationListComponent);
const loadIntegrationEditorComponent = () => import('./pages/integration-editor/integration-editor.component').then((m) => m.IntegrationEditorComponent);
const loadIntegrationHubComponent = () => import('./pages/integration-hub/integration-hub.component').then((m) => m.IntegrationHubComponent);
const loadEmailIntegrationListComponent = () => import('./pages/email-integration-list/email-integration-list.component').then((m) => m.EmailIntegrationListComponent);
const loadEmailIntegrationEditorComponent = () => import('./pages/email-integration-editor/email-integration-editor.component').then((m) => m.EmailIntegrationEditorComponent);
const loadPublicStatusPageComponent = () => import('./pages/public-status-page/public-status-page.component').then((m) => m.PublicStatusPageComponent);
const loadPublicMonitorDetailComponent = () => import('./pages/public-monitor-detail/public-monitor-detail.component').then((m) => m.PublicMonitorDetailComponent);

export const routes: Routes = [
  { path: 'login', loadComponent: loadLoginComponent, title: 'Sign in · Orion Uptime' },
  {
    path: 'status/:slug/:monitorId',
    loadComponent: loadPublicMonitorDetailComponent,
    title: 'Monitor status · Orion Uptime',
  },
  {
    path: 'status/:slug',
    loadComponent: loadPublicStatusPageComponent,
    title: 'Service status · Orion Uptime',
  },
  {
    path: '',
    loadComponent: loadAppShellComponent,
    canActivate: [authGuard],
    children: [
      { path: 'dashboard', loadComponent: loadDashboardComponent, title: 'Dashboard · Orion Uptime' },
      {
        path: 'monitors/http/new',
        loadComponent: loadAddMonitorComponent,
        canActivate: [adminGuard],
        title: 'New HTTP monitor · Orion Uptime',
        data: { kind: 'http', title: 'New HTTP monitor', backUrl: '/monitors/http' },
      },
      {
        path: 'monitors/http/:id/edit',
        loadComponent: loadAddMonitorComponent,
        canActivate: [adminGuard],
        title: 'Edit HTTP monitor · Orion Uptime',
        data: { kind: 'http', title: 'Edit HTTP monitor', backUrl: '/monitors/http' },
      },
      {
        path: 'monitors/http/:id',
        loadComponent: loadMonitorDetailComponent,
        data: { backUrl: '/monitors/http' },
      },
      {
        path: 'monitors/http',
        loadComponent: loadMonitorListComponent,
        data: {
          title: 'HTTP monitors',
          description: 'Website and HTTP endpoint availability checks.',
          resourceType: 'HTTP',
          newUrl: '/monitors/http/new',
          detailBase: '/monitors/http',
          editBase: '/monitors/http',
          deletePath: '/HTTP_monitors/:id/delete',
          updatePath: '/HTTP_monitors/:id/update',
        },
      },
      {
        path: 'monitors/api/new',
        loadComponent: loadAddMonitorComponent,
        canActivate: [adminGuard],
        title: 'New API monitor · Orion Uptime',
        data: { kind: 'api', title: 'New API monitor', backUrl: '/monitors/api' },
      },
      {
        path: 'monitors/api/:id/edit',
        loadComponent: loadAddMonitorComponent,
        canActivate: [adminGuard],
        title: 'Edit API monitor · Orion Uptime',
        data: { kind: 'api', title: 'Edit API monitor', backUrl: '/monitors/api' },
      },
      {
        path: 'monitors/api/:id',
        loadComponent: loadMonitorDetailComponent,
        data: { backUrl: '/monitors/api' },
      },
      {
        path: 'monitors/api',
        loadComponent: loadMonitorListComponent,
        data: {
          title: 'API monitors',
          description: 'Request, response, and protected API checks.',
          resourceType: 'API',
          newUrl: '/monitors/api/new',
          detailBase: '/monitors/api',
          editBase: '/monitors/api',
          deletePath: '/API_monitors/:id',
          updatePath: '/API_monitors/:id',
        },
      },
      {
        path: 'monitors/ping/new',
        loadComponent: loadAddMonitorComponent,
        canActivate: [adminGuard],
        title: 'New Ping monitor · Orion Uptime',
        data: { kind: 'ping', title: 'New Ping monitor', backUrl: '/monitors/ping' },
      },
      {
        path: 'monitors/ping/:id/edit',
        loadComponent: loadAddMonitorComponent,
        canActivate: [adminGuard],
        title: 'Edit Ping monitor · Orion Uptime',
        data: { kind: 'ping', title: 'Edit Ping monitor', backUrl: '/monitors/ping' },
      },
      {
        path: 'monitors/ping/:id',
        loadComponent: loadMonitorDetailComponent,
        data: { backUrl: '/monitors/ping' },
      },
      {
        path: 'monitors/ping',
        loadComponent: loadMonitorListComponent,
        data: {
          title: 'Ping monitors',
          description: 'Operating-system ICMP host checks.',
          resourceType: 'ping',
          newUrl: '/monitors/ping/new',
          detailBase: '/monitors/ping',
          editBase: '/monitors/ping',
          deletePath: '/ping-monitors/:id/delete',
          updatePath: '/ping-monitors/:id/update',
        },
      },
      {
        path: 'monitors/heartbeat/new',
        loadComponent: loadAddMonitorComponent,
        canActivate: [adminGuard],
        title: 'New Heartbeat monitor · Orion Uptime',
        data: {
          kind: 'heartbeat',
          title: 'New Heartbeat monitor',
          backUrl: '/monitors/heartbeat',
        },
      },
      {
        path: 'monitors/heartbeat/:id/edit',
        loadComponent: loadAddMonitorComponent,
        canActivate: [adminGuard],
        title: 'Edit Heartbeat monitor · Orion Uptime',
        data: { kind: 'heartbeat', title: 'Edit Heartbeat monitor', backUrl: '/monitors/heartbeat' },
      },
      {
        path: 'monitors/heartbeat/:id',
        loadComponent: loadMonitorDetailComponent,
        data: { backUrl: '/monitors/heartbeat' },
      },
      {
        path: 'monitors/heartbeat',
        loadComponent: loadMonitorListComponent,
        data: {
          title: 'Heartbeat monitors',
          description: 'Passive client heartbeat listeners.',
          resourceType: 'heartbeat',
          newUrl: '/monitors/heartbeat/new',
          detailBase: '/monitors/heartbeat',
          editBase: '/monitors/heartbeat',
          deletePath: '/heartbeat-monitors/:id/delete',
          updatePath: '/heartbeat-monitors/:id/update',
        },
      },
      {
        path: 'monitors/orion-script/new',
        loadComponent: loadAddMonitorComponent,
        canActivate: [adminGuard],
        title: 'New Orion script monitor · Orion Uptime',
        data: { kind: 'orion-script', title: 'New Orion script monitor', backUrl: '/monitors/orion-script' },
      },
      {
        path: 'monitors/orion-script/:id/edit',
        loadComponent: loadAddMonitorComponent,
        canActivate: [adminGuard],
        title: 'Edit Orion script monitor · Orion Uptime',
        data: { kind: 'orion-script', title: 'Edit Orion script monitor', backUrl: '/monitors/orion-script' },
      },
      {
        path: 'monitors/orion-script/:id',
        loadComponent: loadMonitorDetailComponent,
        data: { backUrl: '/monitors/orion-script' },
      },
      {
        path: 'monitors/orion-script',
        loadComponent: loadMonitorListComponent,
        data: {
          title: 'Orion script monitors',
          description: 'Feeder script health fetched from an Orion Intelligence instance.',
          resourceType: 'orion_script',
          newUrl: '/monitors/orion-script/new',
          detailBase: '/monitors/orion-script',
          editBase: '/monitors/orion-script',
          deletePath: '/orion-script-monitors/:id/delete',
          updatePath: '/orion-script-monitors/:id/update',
        },
      },
      {
        path: 'auth-profiles/new',
        loadComponent: loadAddMonitorComponent,
        canActivate: [adminGuard],
        title: 'New auth profile · Orion Uptime',
        data: { kind: 'auth-profile', title: 'New auth profile', backUrl: '/auth-profiles' },
      },
      {
        path: 'auth-profiles/:id/edit',
        loadComponent: loadAddMonitorComponent,
        canActivate: [adminGuard],
        title: 'Edit auth profile · Orion Uptime',
        data: { kind: 'auth-profile', title: 'Edit auth profile', backUrl: '/auth-profiles' },
      },
      {
        path: 'status-pages/new',
        loadComponent: loadStatusPageEditorComponent,
        canActivate: [adminGuard],
        title: 'New status page · Orion Uptime',
      },
      {
        path: 'status-pages/:id/edit',
        loadComponent: loadStatusPageEditorComponent,
        canActivate: [adminGuard],
        title: 'Edit status page · Orion Uptime',
      },
      {
        path: 'status-pages',
        loadComponent: loadStatusPageListComponent,
        canActivate: [adminGuard],
        title: 'Status pages · Orion Uptime',
      },
      {
        path: 'integrations/slack/new',
        loadComponent: loadIntegrationEditorComponent,
        canActivate: [adminGuard],
        title: 'New Slack integration · Orion Uptime',
      },
      {
        path: 'integrations/slack/:id/edit',
        loadComponent: loadIntegrationEditorComponent,
        canActivate: [adminGuard],
        title: 'Edit Slack integration · Orion Uptime',
      },
      {
        path: 'integrations/slack',
        loadComponent: loadIntegrationListComponent,
        canActivate: [adminGuard],
        title: 'Slack integrations · Orion Uptime',
      },
      {
        path: 'integrations/email/new',
        loadComponent: loadEmailIntegrationEditorComponent,
        canActivate: [adminGuard],
        title: 'New Email integration · Orion Uptime',
      },
      {
        path: 'integrations/email/:id/edit',
        loadComponent: loadEmailIntegrationEditorComponent,
        canActivate: [adminGuard],
        title: 'Edit Email integration · Orion Uptime',
      },
      {
        path: 'integrations/email',
        loadComponent: loadEmailIntegrationListComponent,
        canActivate: [adminGuard],
        title: 'Email integrations · Orion Uptime',
      },
      {
        path: 'integrations',
        loadComponent: loadIntegrationHubComponent,
        canActivate: [adminGuard],
        title: 'Integrations · Orion Uptime',
      },
      {
        path: 'auth-profiles',
        loadComponent: loadMonitorListComponent,
        canActivate: [adminGuard],
        data: {
          title: 'Auth profiles',
          description: 'Credentials used by protected API monitors.',
          resourceType: 'auth_profiles',
          newUrl: '/auth-profiles/new',
          editBase: '/auth-profiles',
          deletePath: '/auth-profiles/:id',
        },
      },
      {
        path: 'users/new',
        loadComponent: loadRegisterUserComponent,
        canActivate: [adminGuard],
        title: 'Register user · Orion Uptime',
      },
      {
        path: 'users',
        loadComponent: loadUserListComponent,
        canActivate: [adminGuard],
        title: 'Registered users · Orion Uptime',
      },
      { path: 'register', pathMatch: 'full', redirectTo: 'users/new' },
      { path: '', pathMatch: 'full', redirectTo: 'dashboard' },
    ],
  },
  { path: '**', redirectTo: 'dashboard' },
];
