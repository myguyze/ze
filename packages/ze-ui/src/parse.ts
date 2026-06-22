import { PrimitiveValidationError } from "./errors";
import {
  primitiveTreeValidationErrors,
  primitiveValidationErrors,
  runPrimitiveTreeValidator,
  runPrimitiveValidator,
} from "./generated/validators.gen";
import type { Primitive } from "./generated/types.gen";

export type PrimitiveTree = Primitive[];
export type PrimitiveNode = Primitive;
export type PrimitiveAction = string;

export function validatePrimitive(data: unknown): data is Primitive {
  return runPrimitiveValidator(data);
}

export function validatePrimitiveTree(data: unknown): data is PrimitiveTree {
  return runPrimitiveTreeValidator(data);
}

export function parsePrimitive(data: unknown): Primitive {
  if (!runPrimitiveValidator(data)) {
    throw PrimitiveValidationError.fromAjvErrors(primitiveValidationErrors(data));
  }
  return data as Primitive;
}

export function parsePrimitiveTree(data: unknown): PrimitiveTree {
  if (!runPrimitiveTreeValidator(data)) {
    throw PrimitiveValidationError.fromAjvErrors(primitiveTreeValidationErrors(data));
  }
  return data as PrimitiveTree;
}
