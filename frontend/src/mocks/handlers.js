import { http, HttpResponse } from 'msw';

export const handlers = [
  http.post('*/api/auth/login', () => {
    return HttpResponse.json({
      access_token: 'test-jwt-token',
      id: '1',
      username: 'testlab',
      role: 'LAB',
      name: 'Test Lab User',
    });
  }),
  http.post('*/api/auth/refresh', () => {
    return HttpResponse.json({ access_token: 'refreshed-jwt-token' });
  }),
  http.get('*/api/auth/me', () => {
    return HttpResponse.json({
      id: '1',
      username: 'testlab',
      role: 'LAB',
      name: 'Test Lab User',
    });
  }),
  http.get('*/api/screening/work-queue*', () => {
    return HttpResponse.json({
      counts: { pending: 5, in_progress: 2, completed: 10 },
      items: [
        {
          id: 'scr-001',
          patientId: 'P000001',
          labId: 'LAB-001',
          riskClass: 3,
          labelText: 'Deficient',
          status: 'pending',
          createdAt: '2026-01-01T00:00:00Z',
          performedBy: 'testlab',
        },
      ],
      pagination: { page: 1, page_size: 50, total: 1 },
    });
  }),
];
