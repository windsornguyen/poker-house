// Copyright 2026 DeepMind Technologies Limited
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//      http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import {describe, expect, it} from 'vite-plus/test';

import {ROOT_NAME, schemaToZod} from './generate_contract.ts';

/** The schema of a contract whose one response is `Body`. */
function contract(body: object, extra: Record<string, object> = {}): object {
  return {
    oneOf: [{$ref: '#/$defs/Body'}],
    $defs: {Body: body, ...extra},
  };
}

/** The declaration of `Body`, on one line. */
function body(schema: object, extra: Record<string, object> = {}): string {
  const source = schemaToZod(contract(schema, extra));
  const start = source.indexOf('export const Body');
  return source.slice(start, source.indexOf('});\n', start) + 3);
}

function object(properties: Record<string, object>): object {
  return {
    type: 'object',
    properties,
    required: Object.keys(properties),
    additionalProperties: false,
  };
}

describe('schemaToZod translations', () => {
  it('declares the root as the union of the responses', () => {
    expect(schemaToZod(contract(object({})))).toContain(
      `export const ${ROOT_NAME} = Body;`,
    );
  });

  it.each([
    [{type: 'string'}, 'z.string()'],
    [{type: 'integer'}, 'z.int()'],
    [
      {type: ['integer', 'number', 'null']},
      'z.union([z.int(), z.number(), z.null()])',
    ],
    [{type: 'boolean'}, 'z.boolean()'],
    [{const: 1}, 'z.literal(1)'],
    [{enum: ['a', 'b']}, 'z.enum(["a","b"])'],
    [{type: 'string', enum: ['a', 'b']}, 'z.enum(["a","b"])'],
    [{type: ['string', 'null'], enum: ['a', null]}, 'z.literal(["a",null])'],
    [{type: 'number', const: 1.5}, 'z.literal(1.5)'],
    [{$ref: '#/$defs/Other'}, 'Other'],
    [{type: 'array', items: {type: 'integer'}}, 'z.array(z.int())'],
    [
      {type: 'array', items: {type: ['string', 'null']}},
      'z.array(z.string().nullable())',
    ],
    [{type: 'array', items: {$ref: '#/$defs/Other'}}, 'z.array(Other)'],
    [
      {type: 'array', items: {type: 'array', items: {type: 'integer'}}},
      'z.array(z.array(z.int()))',
    ],
    [
      {type: 'array', items: {type: 'object', additionalProperties: true}},
      'z.array(z.record(z.string(), z.unknown()))',
    ],
    [
      {anyOf: [{type: 'array', items: {type: 'integer'}}, {type: 'null'}]},
      'z.array(z.int()).nullable()',
    ],
    [
      {type: 'object', additionalProperties: {type: 'boolean'}},
      'z.record(z.string(), z.boolean())',
    ],
    [
      {type: 'object', additionalProperties: {}},
      'z.record(z.string(), z.unknown())',
    ],
    [{description: 'Any JSON value.'}, 'z.unknown()'],
  ])('translates %j to %s', (schema, type) => {
    const other = {Other: object({})};
    expect(body(object({field: schema}), other)).toContain(`field: ${type},`);
  });

  it('marks a property that is not required as optional', () => {
    const schema = {...object({field: {type: 'string'}}), required: []};
    expect(body(schema)).toContain('field: z.string().exactOptional(),');
  });

  it('declares an enum definition as a schema and its type', () => {
    const source = schemaToZod(
      contract(object({}), {Kind: {type: 'string', enum: ['x', 'y']}}),
    );
    expect(source).toContain(
      'export const Kind = z.enum(["x","y"]);\nexport type Kind = z.infer<typeof Kind>;',
    );
  });

  it('turns descriptions into doc comments, escaping their end', () => {
    const schema = {
      ...object({field: {type: 'string', description: 'A */ B'}}),
      description: 'First.\n\nSecond.',
    };
    const source = schemaToZod(contract(schema));
    expect(source).toContain('/**\n * First.\n *\n * Second.\n */\n');
    expect(source).toContain(
      '  /**\n   * A *\\/ B\n   */\n  field: z.string(),',
    );
  });
});

describe('schemaToZod refusals', () => {
  it.each([
    [{type: 'string', format: 'date'}, 'unsupported keyword format'],
    [{type: 'object', $defs: {}}, 'unsupported keyword $defs'],
    [{$schema: 'x'}, 'unsupported keyword $schema'],
    [{$ref: 'other.json#/Thing'}, 'unsupported $ref other.json#/Thing'],
    [{type: 'tuple'}, 'unsupported type tuple'],
    [{type: 'object'}, 'an object needs properties or their values'],
    [
      {type: 'object', properties: {}, additionalProperties: false},
      'an object with properties must be a $defs definition',
    ],
    [{type: 'array'}, 'an array needs items'],
    [{items: {type: 'string'}}, 'items without type array'],
    [{type: 'string', required: []}, 'required without type object'],
    [{$ref: '#/$defs/Other', type: 'object'}, '$ref together with type'],
    [{enum: ['a'], const: 'a'}, 'const together with enum'],
    [{type: 'string', enum: [1, null]}, '1, null not of type string'],
    [{type: 'integer', const: 1.5}, '1.5 not of type integer'],
    [{type: 1}, 'type must be a string or a non-empty array of strings'],
    [{type: []}, 'type must be a string or a non-empty array of strings'],
    [{type: 'string', description: 1}, 'description must be a string'],
    [{$ref: 1}, '$ref must be a string'],
    [{type: 'string', enum: 'x'}, 'enum must be an array'],
    [{anyOf: {type: 'string'}}, 'anyOf must be an array'],
    [{oneOf: {type: 'string'}}, 'oneOf must be an array'],
    [{type: 'array', items: true}, 'items must be a schema'],
    [
      {type: 'object', additionalProperties: 'x'},
      'additionalProperties must be a boolean or a schema',
    ],
  ])('refuses the property %j', (schema, message) => {
    expect(() => schemaToZod(contract(object({field: schema})))).toThrow(
      `#/$defs/Body/properties/field: ${message}`,
    );
  });

  it('gives the pointer into the values of a record', () => {
    const field = {type: 'object', additionalProperties: {format: 'x'}};
    expect(() => schemaToZod(contract(object({field})))).toThrow(
      '#/$defs/Body/properties/field/additionalProperties: unsupported keyword format',
    );
  });

  it.each([
    [{required: 'field'}, 'required must be an array of strings'],
    [{required: [1]}, 'required must be an array of strings'],
    [{required: ['toString']}, 'requires undeclared toString'],
    [
      {additionalProperties: true},
      'an object definition must refuse extra properties',
    ],
    [{type: 'array'}, 'properties without type object'],
    [{enum: [{}]}, 'properties together with enum'],
  ])('refuses the definition change %j', (change, message) => {
    const schema = {...object({field: {type: 'string'}}), ...change};
    expect(() => schemaToZod(contract(schema))).toThrow(
      `#/$defs/Body: ${message}`,
    );
  });

  it('refuses a property name that is not an identifier', () => {
    expect(() =>
      schemaToZod(contract(object({'two words': {type: 'string'}}))),
    ).toThrow('#/$defs/Body/properties/two words: not a TypeScript identifier');
  });

  it('refuses a definition name that is not an identifier', () => {
    expect(() =>
      schemaToZod(contract(object({}), {'two words': object({})})),
    ).toThrow('#/$defs/two words: not a TypeScript identifier');
  });

  it.each([
    [{$defs: {}}, '#: the root needs $defs and oneOf'],
    [{oneOf: []}, '#: the root needs $defs and oneOf'],
    [{oneOf: [], $defs: {}, type: 'object'}, '#: unsupported keyword type'],
  ])('refuses the root %j', (root, message) => {
    expect(() => schemaToZod(root)).toThrow(message);
  });
});

describe('schemaToZod order', () => {
  it('declares each definition after those it refers to', () => {
    const source = schemaToZod(
      contract(object({field: {$ref: '#/$defs/Other'}}), {Other: object({})}),
    );
    expect(source.indexOf('export const Other')).toBeLessThan(
      source.indexOf('export const Body'),
    );
  });

  it('refuses a $ref cycle', () => {
    const cycle = object({field: {$ref: '#/$defs/Body'}});
    expect(() => schemaToZod(contract(cycle))).toThrow(
      '#/$defs/Body: a $ref cycle through Body',
    );
  });
});
