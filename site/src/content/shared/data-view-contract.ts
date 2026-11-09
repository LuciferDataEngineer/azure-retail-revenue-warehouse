export type ColumnKind = "string" | "number" | "boolean" | "date" | "unknown";
export type Column = ColumnKind | { type: ColumnKind; nullable?: boolean; optional?: boolean };
export type QueryContract = { columns: Record<string, Column>; breakdown?: readonly string[] };
export type DataViewSchema = Record<string, QueryContract>;
type Kind<C extends Column> = C extends ColumnKind ? C : C extends { type: infer K } ? K : never;
type Cell<C extends Column> = (Kind<C> extends "unknown" ? unknown : Kind<C> extends "number" ? number : Kind<C> extends "boolean" ? boolean : string)
  | (C extends { nullable: true } ? null : never) | (C extends { optional: true } ? undefined : never);
export type ReviewedRow<Q extends QueryContract> = { readonly [K in keyof Q["columns"]]: Cell<Q["columns"][K]> };
export type CheckedSchema<S extends DataViewSchema> = {
  [K in keyof S]: { breakdown?: readonly Extract<keyof S[K]["columns"], string>[] };
};

export function assertDataViewSchema(schema: DataViewSchema) {
  for (const [query, contract] of Object.entries(schema)) {
    for (const field of contract.breakdown ?? [])
      if (!Object.hasOwn(contract.columns, field)) throw new Error(`Data view: ${query} breakdown has no declared ${field} field.`);
  }
}

export function assertReviewedRows<Q extends QueryContract>(query: string, contract: Q, rows: unknown): asserts rows is ReviewedRow<Q>[] {
  if (!Array.isArray(rows)) throw new Error(`Data view: ${query} has no loaded reviewed rows.`);
  const fields = Object.entries(contract.columns);
  for (const [index, row] of rows.entries()) {
    if (!row || typeof row !== "object" || Array.isArray(row)) throw new Error(`Data view: ${query} row ${index + 1} is not a record.`);
    for (const [field, column] of fields) {
      const definition = typeof column === "string" ? { type: column } : column;
      const value = row[field];
      if (value === undefined && definition.optional || value === null && definition.nullable) continue;
      const valid = value !== undefined && value !== null && (definition.type === "unknown" || (definition.type === "date"
        ? typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value)
          && Number.isFinite(Date.parse(value)) && new Date(value).toISOString().slice(0, 10) === value
        : typeof value === definition.type && (definition.type !== "number" || Number.isFinite(value))));
      if (!valid) throw new Error(`Data view: ${query}.${field} row ${index + 1} must be ${definition.type}${definition.nullable ? " or null" : ""}.`);
    }
  }
}

export function assertFilterFields(schema: DataViewSchema, filters: readonly { id: string; field: string; queryIds?: readonly string[] }[]) {
  for (const filter of filters) {
    for (const [query, contract] of Object.entries(schema)) {
      if ((!filter.queryIds || filter.queryIds.includes(query)) && !Object.hasOwn(contract.columns, filter.field))
        throw new Error(`Data view: filter ${filter.id} targets ${query}, which has no ${filter.field} field. Declare its queryIds or correct the contract.`);
    }
  }
}
