// Flat Config (ESLint 10). Bewusst schlank: js/ts-recommended + React-Hooks-Regeln,
// keine Format-Regeln (Formatierung ist nicht Aufgabe des Linters).
import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist", "src/types/api.gen.ts"] },
  js.configs.recommended,
  tseslint.configs.recommended,
  reactHooks.configs.flat.recommended,
);
