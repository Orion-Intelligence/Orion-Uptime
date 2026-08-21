import { Routes } from '@angular/router';
import { adminGuard, authGuard } from './guards/auth.guard';
import { AppShell } from './layout/app-shell/app-shell';
import { DashboardPage } from './pages/dashboard/dashboard';
import { LoginPage } from './pages/login/login';
import { NewResourcePage } from './pages/add-monitor/add-monitor';
import { MonitorDetailPage } from './pages/monitor-detail/monitor-detail';
import { RegisterUserPage } from './pages/register-user/register-user';
import { ResourceListPage } from './pages/monitor-list/monitor-list';
import { UserListPage } from './pages/user-list/user-list';
import { StatusPageListPage } from './pages/status-page-list/status-page-list';
import { StatusPageEditorPage } from './pages/status-page-editor/status-page-editor';
import { PublicStatusPageView } from './pages/public-status-page/public-status-page';
import { PublicMonitorDetailPage } from './pages/public-monitor-detail/public-monitor-detail';

export const routes: Routes = [
  { path: 'login', component: LoginPage, title: 'Sign in · Orion Uptime' },
  {
    path: 'status/:slug/:monitorId',
    component: PublicMonitorDetailPage,
    title: 'Monitor status · Orion Uptime',
  },
  {
    path: 'status/:slug',
    component: PublicStatusPageView,
    title: 'Service status · Orion Uptime',
  },
  {
    path: '',
    component: AppShell,
    canActivate: [authGuard],
    children: [
      { path: 'dashboard', component: DashboardPage, title: 'Dashboard · Orion Uptime' },
      {
        path: 'monitors/http/new',
        component: NewResourcePage,
        canActivate: [adminGuard],
        title: 'New HTTP monitor · Orion Uptime',
        data: { kind: 'http', title: 'New HTTP monitor', backUrl: '/monitors/http' },
      },
      {
        path: 'monitors/http/:id',
        component: MonitorDetailPage,
        data: { backUrl: '/monitors/http' },
      },
      {
        path: 'monitors/http',
        component: ResourceListPage,
        data: {
          title: 'HTTP monitors',
          description: 'Website and HTTP endpoint availability checks.',
          resourceType: 'HTTP',
          newUrl: '/monitors/http/new',
          detailBase: '/monitors/http',
          deletePath: '/HTTP_monitors/:id/delete',
          updatePath: '/HTTP_monitors/:id/update',
        },
      },
      {
        path: 'monitors/api/new',
        component: NewResourcePage,
        canActivate: [adminGuard],
        title: 'New API monitor · Orion Uptime',
        data: { kind: 'api', title: 'New API monitor', backUrl: '/monitors/api' },
      },
      {
        path: 'monitors/api/:id',
        component: MonitorDetailPage,
        data: { backUrl: '/monitors/api' },
      },
      {
        path: 'monitors/api',
        component: ResourceListPage,
        data: {
          title: 'API monitors',
          description: 'Request, response, and protected API checks.',
          resourceType: 'API',
          newUrl: '/monitors/api/new',
          detailBase: '/monitors/api',
          deletePath: '/API_monitors/:id',
          updatePath: '/API_monitors/:id',
        },
      },
      {
        path: 'monitors/ping/new',
        component: NewResourcePage,
        canActivate: [adminGuard],
        title: 'New Ping monitor · Orion Uptime',
        data: { kind: 'ping', title: 'New Ping monitor', backUrl: '/monitors/ping' },
      },
      {
        path: 'monitors/ping/:id',
        component: MonitorDetailPage,
        data: { backUrl: '/monitors/ping' },
      },
      {
        path: 'monitors/ping',
        component: ResourceListPage,
        data: {
          title: 'Ping monitors',
          description: 'Operating-system ICMP host checks.',
          resourceType: 'ping',
          newUrl: '/monitors/ping/new',
          detailBase: '/monitors/ping',
          deletePath: '/ping-monitors/:id/delete',
          updatePath: '/ping-monitors/:id/update',
        },
      },
      {
        path: 'monitors/heartbeat/new',
        component: NewResourcePage,
        canActivate: [adminGuard],
        title: 'New Heartbeat monitor · Orion Uptime',
        data: {
          kind: 'heartbeat',
          title: 'New Heartbeat monitor',
          backUrl: '/monitors/heartbeat',
        },
      },
      {
        path: 'monitors/heartbeat/:id',
        component: MonitorDetailPage,
        data: { backUrl: '/monitors/heartbeat' },
      },
      {
        path: 'monitors/heartbeat',
        component: ResourceListPage,
        data: {
          title: 'Heartbeat monitors',
          description: 'Passive client heartbeat listeners.',
          resourceType: 'heartbeat',
          newUrl: '/monitors/heartbeat/new',
          detailBase: '/monitors/heartbeat',
          deletePath: '/heartbeat-monitors/:id/delete',
          updatePath: '/heartbeat-monitors/:id/update',
        },
      },
      {
        path: 'auth-profiles/new',
        component: NewResourcePage,
        canActivate: [adminGuard],
        title: 'New auth profile · Orion Uptime',
        data: { kind: 'auth-profile', title: 'New auth profile', backUrl: '/auth-profiles' },
      },
      {
        path: 'status-pages/new',
        component: StatusPageEditorPage,
        canActivate: [adminGuard],
        title: 'New status page · Orion Uptime',
      },
      {
        path: 'status-pages/:id/edit',
        component: StatusPageEditorPage,
        canActivate: [adminGuard],
        title: 'Edit status page · Orion Uptime',
      },
      {
        path: 'status-pages',
        component: StatusPageListPage,
        canActivate: [adminGuard],
        title: 'Status pages · Orion Uptime',
      },
      {
        path: 'auth-profiles',
        component: ResourceListPage,
        canActivate: [adminGuard],
        data: {
          title: 'Auth profiles',
          description: 'Credentials used by protected API monitors.',
          resourceType: 'auth_profiles',
          newUrl: '/auth-profiles/new',
          deletePath: '/auth-profiles/:id',
        },
      },
      {
        path: 'users/new',
        component: RegisterUserPage,
        canActivate: [adminGuard],
        title: 'Register user · Orion Uptime',
      },
      {
        path: 'users',
        component: UserListPage,
        canActivate: [adminGuard],
        title: 'Registered users · Orion Uptime',
      },
      { path: 'register', pathMatch: 'full', redirectTo: 'users/new' },
      { path: '', pathMatch: 'full', redirectTo: 'dashboard' },
    ],
  },
  { path: '**', redirectTo: 'dashboard' },
];
