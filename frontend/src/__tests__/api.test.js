import '@testing-library/jest-dom';

// Mock the api module internals
// Variables prefixed with `mock` are allowed inside jest.mock() factory
let mockInterceptors = { request: [], response: [] };
let mockAxiosInstance;

jest.mock('axios', () => {
  const mockCreate = jest.fn(() => {
    mockAxiosInstance = {
      interceptors: {
        request: {
          use: jest.fn((fn) => {
            mockInterceptors.request.push(fn);
          }),
        },
        response: {
          use: jest.fn((onFulfilled, onRejected) => {
            mockInterceptors.response.push({ onFulfilled, onRejected });
          }),
        },
      },
      get: jest.fn(),
      post: jest.fn(),
      defaults: { headers: { common: {} } },
    };
    return mockAxiosInstance;
  });
  return { create: mockCreate, default: { create: mockCreate } };
});

describe('API Service', () => {
  beforeEach(() => {
    mockInterceptors = { request: [], response: [] };
    jest.resetModules();
  });

  test('module loads without error', () => {
    expect(() => require('../services/api')).not.toThrow();
  });
});
