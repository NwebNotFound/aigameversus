// Writes a small, fixed OpenRouter model list as the arena's catalog cache, so a test
// stack lists the same models every run and never downloads the real list.
// Usage: node tests/fixtures/catalog-cache.mjs <path>; start the arena with
// ARENA_CATALOG_CACHE=<path>. The entries are made up: none of them is a real price.
import { writeFileSync } from 'node:fs';

const tools = ['tools', 'tool_choice', 'max_tokens'];
const text = { output_modalities: ['text'] };

const data = [
	{
		id: 'testvendor/cheap-chat',
		name: 'Test Cheap Chat',
		context_length: 64000,
		pricing: { prompt: '0.0000001', completion: '0.0000002' },
		supported_parameters: tools,
		architecture: text
	},
	{
		id: 'testvendor/thinker-pro',
		name: 'Test Thinker Pro',
		context_length: 200000,
		pricing: { prompt: '0.000015', completion: '0.00006' },
		supported_parameters: [...tools, 'reasoning'],
		architecture: text
	},
	{
		id: 'testvendor/free-mini:free',
		name: 'Test Free Mini',
		context_length: 8000,
		pricing: { prompt: '0', completion: '0' },
		supported_parameters: tools,
		architecture: text
	},
	{
		id: 'testvendor/no-tools',
		name: 'Test No Tools',
		context_length: 8000,
		pricing: { prompt: '0.0000001', completion: '0.0000001' },
		supported_parameters: ['max_tokens'],
		architecture: text
	}
];

const path = process.argv[2];
if (!path) throw new Error('give the cache path');
writeFileSync(path, JSON.stringify({ fetched_at: Date.now() / 1000, data }));
console.log(`catalog cache with ${data.length} entries written to ${path}`);
