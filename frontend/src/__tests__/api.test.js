import '@testing-library/jest-dom';

// Mock the api module internals
let interceptors = { request: [], response: [] };
let mockAxiosInstance;

jest.mock('axios', () => {
  const mockCreate = jest.fn(() => {
    mockAxiosInstance = {
      interceptors: {
        request: {
          use: jest.fn((fn) => {
            interceptors.request.push(fn);
          }),
        },
        response: {
          use: jest.fn((onFulfilled, onRejected) => {
            interceptors.response.push({ onFulfilled, onRejected });
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
    interceptors = { request: [], response: [] };
    jest.resetModules();
  });

  test('module loads without error', () => {
    expect(() => require('../services/api')).not.toThrow();
  });
});
