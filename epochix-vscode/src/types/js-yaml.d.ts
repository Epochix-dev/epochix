// js-yaml ships no types. Only `load` is used, to read a project's
// `.epochix.yaml` (story/gradeConfig.ts).
declare module "js-yaml" {
  export function load(text: string): unknown;
}
