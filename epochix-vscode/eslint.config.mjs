// Flat config. ESLint 9 dropped .eslintrc entirely, so this is a port of the
// previous .eslintrc.json rather than a rewrite — every rule below was already
// enforced, and the two that matter most are kept deliberately:
//
//   no-floating-promises  — this extension is almost entirely async, and a
//                           dropped promise is a feature that silently does
//                           nothing, which is the failure mode that has cost
//                           the most here.
//   no-misused-promises   — an async handler passed where a sync one is
//                           expected fails the same silent way.
import js from "@eslint/js";
import tseslint from "typescript-eslint";

export default tseslint.config(
  {
    // Replaces ignorePatterns. Must come first and stand alone to apply
    // globally in flat config.
    ignores: ["out/**", "dist/**", "node_modules/**", "**/*.js", "**/*.mjs"],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  ...tseslint.configs.recommendedTypeChecked,
  {
    languageOptions: {
      parserOptions: {
        project: ["./tsconfig.json", "./tsconfig.test.json"],
        tsconfigRootDir: import.meta.dirname,
      },
    },
    rules: {
      "@typescript-eslint/no-floating-promises": "error",
      "@typescript-eslint/no-misused-promises": "error",
      "@typescript-eslint/await-thenable": "error",
      "@typescript-eslint/no-unnecessary-type-assertion": "error",
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
      "no-console": ["warn", { allow: ["warn", "error"] }],
      eqeqeq: ["error", "always", { null: "ignore" }],
      "prefer-const": "error",
      "no-throw-literal": "error",
    },
  },
  {
    // Test code drives untyped VS Code test doubles; `any` is unavoidable
    // there and turning these on would only teach people to ignore the linter.
    files: ["src/test/**/*.ts"],
    rules: {
      "@typescript-eslint/no-unsafe-member-access": "off",
      "@typescript-eslint/no-unsafe-assignment": "off",
      "@typescript-eslint/no-unsafe-call": "off",
    },
  },
);
