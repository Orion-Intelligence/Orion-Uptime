import { testId } from './shared.controller';

export const LOG_MANAGER_PATH = '/log-manager';
export const SYSTEM_LOGS_API = '**/api/system-logs*';

export interface LogEntryStub {
  type: string;
  time: string;
  file: string;
  source: string;
  message: string;
}

export const buildLogPage = (page: number, logs: LogEntryStub[], hasMore: boolean, sourceProfileName: string | null = 'orion test') => ({
  success: true,
  message: 'System logs retrieved successfully.',
  data: { logs, page, limit: 200, total: logs.length, has_more: hasMore, source_profile_name: sourceProfileName },
});

export const searchParam = (url: string, key: string): string | null => new URL(url).searchParams.get(key);

export const openLogManager = () => {
  cy.get(testId('nav-log-manager')).click();
  cy.location('pathname').should('eq', LOG_MANAGER_PATH);
  cy.get(testId('log-manager-page')).should('be.visible');
  cy.get(testId('page-title')).should('contain.text', 'Log Manager');
};
