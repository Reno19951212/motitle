/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_CONSOLE: string | undefined;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
