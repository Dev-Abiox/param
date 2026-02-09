export enum Role {
  LAB = 'LAB',
  ADMIN = 'ADMIN',
  PUBLIC = 'PUBLIC'
}

export enum Flag {
  LOW = 'L',
  NORMAL = 'N',
  HIGH = 'H'
}

export enum ScreeningLabel {
  NORMAL = 1,
  BORDERLINE = 2,
  DEFICIENT = 3
}

export interface User {
  id: string;
  name: string;
  role: Role;
}

export interface PatientData {
  id: string;
  name: string;
  age: number;
  sex: 'M' | 'F';
  date: string;
  labId: string;
  referringDoctor?: string;
}

export interface CBCRow {
  test: string;
  key: string; // internal key for API
  value: string; // string to allow empty state during typing
  unit: string;
  refRangeM: [number, number];
  refRangeF: [number, number];
}

export interface CBCResult {
  [key: string]: number;
}

export interface ScreeningResult {
  label: ScreeningLabel;
  probabilities: {
    normal: number;
    borderline: number;
    deficient: number;
  };
  indices: {
    mentzer: number;
    greenKing: number;
    nlr: number;
    pancytopenia: number;
  };
  recommendation: string;
  interpretation: string;
}