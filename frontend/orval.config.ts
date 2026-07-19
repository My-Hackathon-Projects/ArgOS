import { defineConfig } from "orval";

// Generates the typed API client + TanStack Query hooks from the backend's OpenAPI
// schema (Pydantic response_models -> backend/openapi.json). Regenerate with `npm run api:gen`.
// The generated dir is committed; CI fails if regenerating produces a diff (schema drift).
export default defineConfig({
  vcbrain: {
    input: "../backend/openapi.json",
    output: {
      mode: "tags-split",
      target: "src/api/generated/endpoints.ts",
      schemas: "src/api/generated/model",
      client: "react-query",
      httpClient: "axios",
      clean: true,
      override: {
        mutator: { path: "src/api/axios-instance.ts", name: "customInstance" },
      },
    },
  },
});
