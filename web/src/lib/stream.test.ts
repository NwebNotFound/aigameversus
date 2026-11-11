import { describe, expect, it } from 'vitest';
import { relay } from './stream.js';

/** A WebSocket the test drives: `receive` sends a message, `close` ends it. */
class FakeSocket {
	onmessage: ((message: { data: string }) => void) | null = null;
	onclose: ((closed: { code: number }) => void) | null = null;
	onerror: (() => void) | null = null;
	closed = false;

	receive(body: unknown) {
		this.onmessage?.({ data: typeof body === 'string' ? body : JSON.stringify(body) });
	}

	close(code = 1005) {
		this.closed = true;
		this.onclose?.({ code });
	}
}

function open(lastSeen = -1, onlyPublic = false) {
	const sockets: { url: string; socket: FakeSocket }[] = [];
	const stream = relay('ws://arena/matches/m1/events', lastSeen, onlyPublic, (url) => {
		const socket = new FakeSocket();
		sockets.push({ url, socket });
		return socket as unknown as WebSocket;
	});
	return { stream, sockets };
}

async function readAll(stream: ReadableStream<Uint8Array>): Promise<string> {
	return new Response(stream).text();
}

describe('relay', () => {
	it('sends each event with its position as the id, then the end', async () => {
		const { stream, sockets } = open();
		const { url, socket } = sockets[0];

		socket.receive({ seq: 0, type: 'match_started' });
		socket.receive({ seq: 1, type: 'round_started' });
		socket.close(1000);

		expect(url).toBe('ws://arena/matches/m1/events');
		expect(await readAll(stream)).toBe(
			'retry: 2000\n\n' +
				'id: 0\nevent: event\ndata: {"seq":0,"type":"match_started"}\n\n' +
				'id: 1\nevent: event\ndata: {"seq":1,"type":"round_started"}\n\n' +
				'event: end\ndata: {}\n\n'
		);
	});

	it('skips what the browser already has after a reconnect', async () => {
		const { stream, sockets } = open(1);
		const { socket } = sockets[0];

		// The arena sends a log from its start, every time.
		for (const seq of [0, 1, 2]) socket.receive({ seq });
		socket.close(1000);

		const body = await readAll(stream);
		expect(body).not.toContain('id: 0\n');
		expect(body).not.toContain('id: 1\n');
		expect(body).toContain('id: 2\nevent: event\ndata: {"seq":2}\n\n');
	});

	it('says when the arena knows no such match', async () => {
		const { stream, sockets } = open();

		sockets[0].socket.close(4404);

		expect(await readAll(stream)).toBe('retry: 2000\n\nevent: missing\ndata: {}\n\n');
	});

	it('ends without an end event when the connection breaks, so the browser reconnects', async () => {
		const { stream, sockets } = open();

		sockets[0].socket.receive({ seq: 0 });
		sockets[0].socket.close(1006);

		const body = await readAll(stream);
		expect(body).toContain('id: 0\n');
		expect(body).not.toContain('event: end');
	});

	it('ignores a message that is not an event', async () => {
		const { stream, sockets } = open();

		sockets[0].socket.receive('not json');
		sockets[0].socket.receive({ type: 'no seq' });
		sockets[0].socket.close(1000);

		expect(await readAll(stream)).toBe('retry: 2000\n\nevent: end\ndata: {}\n\n');
	});

	it('sends only public events to a spoiler-free page', async () => {
		const { stream, sockets } = open(-1, true);
		const { socket } = sockets[0];

		socket.receive({ seq: 0, type: 'match_started', data: { seed: 7 }, visible_to: [] });
		socket.receive({ seq: 1, type: 'thought', data: { text: 'I bluff' }, visible_to: [] });
		socket.receive({ seq: 2, type: 'hand_dealt', data: { cards: ['K1'] }, visible_to: ['p1'] });
		socket.receive({ seq: 3, type: 'cards_played', data: { count: 1 }, visible_to: null });
		socket.close(1000);

		const body = await readAll(stream);
		expect(body).toContain('id: 3\n');
		for (const secret of ['seed', 'I bluff', 'K1', 'id: 0', 'id: 1', 'id: 2']) {
			expect(body).not.toContain(secret);
		}
	});

	it('closes the arena socket when the browser goes away', async () => {
		const { stream, sockets } = open();

		await stream.cancel();

		expect(sockets[0].socket.closed).toBe(true);
	});
});
