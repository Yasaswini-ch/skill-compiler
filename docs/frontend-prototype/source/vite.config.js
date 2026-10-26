import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { viteSingleFile } from 'vite-plugin-singlefile';

// One self-contained HTML file: opens from a folder (file://) and needs no internet.
export default defineConfig({
  plugins: [react(), viteSingleFile()],
  base: './'
});
