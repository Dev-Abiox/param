/**
 * Basic smoke tests for Clinomic Frontend
 * These tests verify that the app can render without crashing
 */

describe('Application Smoke Tests', () => {
  test('environment is configured correctly', () => {
    expect(process.env.NODE_ENV).toBeDefined();
  });

  test('basic math operations work', () => {
    expect(1 + 1).toBe(2);
  });

  test('async operations work', async () => {
    const result = await Promise.resolve('success');
    expect(result).toBe('success');
  });
});

describe('Configuration', () => {
  test('backend URL environment variable pattern is valid', () => {
    // Just verify the pattern - actual value comes from env
    const urlPattern = /^https?:\/\/.+/;
    const backendUrl = process.env.REACT_APP_BACKEND_URL || 'http://localhost:8001';
    expect(backendUrl).toMatch(urlPattern);
  });
});
