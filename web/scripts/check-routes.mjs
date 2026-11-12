// A spec that routes network calls must take `test` from tests/routes.ts, whose `page`
// unroutes at teardown: a handler that outlives its test otherwise fails a green run.
import { readdirSync, readFileSync } from 'node:fs';

const bad = readdirSync('tests')
	.filter((file) => file.endsWith('.spec.ts'))
	.filter((file) => {
		const text = readFileSync(`tests/${file}`, 'utf-8');
		const routes = /\bpage\.route\(|\bcontext\.route\(/.test(text);
		const safe = /from '\.\/routes(\.js)?'/.test(text);
		return routes && !safe;
	});

if (bad.length) {
	console.error(
		`These specs call page.route but do not import test from './routes.js': ${bad.join(', ')}`
	);
	process.exit(1);
}
