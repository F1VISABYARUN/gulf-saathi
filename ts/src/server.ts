// Start the Gulf Saathi server: node dist/server.js (PORT defaults to 8000).
import { createApp } from './api.js';

const port = Number(process.env.PORT || 8000);
createApp().listen(port, () => console.log(`Gulf Saathi listening on port ${port}`));
