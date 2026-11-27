// Copies the agent list and public files next to the built server, so dist/ runs on its own.
import { cpSync, mkdirSync } from 'node:fs';
mkdirSync('dist/data', { recursive: true });
mkdirSync('dist/styles', { recursive: true });
cpSync('../data/licensed_agents.csv', 'dist/data/licensed_agents.csv');
cpSync('../public', 'dist/public', { recursive: true });
cpSync('src/tables', 'dist/tables', { recursive: true });
cpSync('src/styles/dashboard.built.css', 'dist/styles/dashboard.built.css');
