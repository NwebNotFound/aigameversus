/**
 * Turns the arena's WebSocket event stream into server-sent events.
 *
 * SSE event types:
 * - `event`: one log event as JSON, with its `seq` as the SSE id;
 * - `end`: the match has stopped and the whole log was sent (WebSocket close 1000);
 * - `missing`: the arena knows no such match (close 4404).
 *
 * Any other close (the arena restarted, the network broke) just ends the response.
 * The EventSource then reconnects by itself and the relay resumes after `lastSeen`.
 * With `onlyPublic`, events that not every player could see are not sent at all.
 */

const UNKNOWN_MATCH = 4404;
const RETRY_MS = 2000;

export function relay(
	url: string,
	lastSeen: number,
	onlyPublic = false,
	connect: (url: string) => WebSocket = (u) => new WebSocket(u)
): ReadableStream<Uint8Array> {
	const encoder = new TextEncoder();
	let socket: WebSocket | undefined;
	let open = true;

	return new ReadableStream({
		start(controller) {
			const send = (text: string) => {
				if (open) controller.enqueue(encoder.encode(text));
			};
			const finish = () => {
				if (!open) return;
				open = false;
				controller.close();
			};

			send(`retry: ${RETRY_MS}\n\n`);
			socket = connect(url);
			socket.onmessage = (message) => {
				const text = String(message.data);
				let event: { seq?: unknown; visible_to?: unknown };
				try {
					event = JSON.parse(text);
				} catch {
					return;
				}
				const seq = event.seq;
				if (typeof seq !== 'number' || seq <= lastSeen) return;
				if (onlyPublic && event.visible_to !== null) return;
				send(`id: ${seq}\nevent: event\ndata: ${text}\n\n`);
			};
			socket.onclose = (closed) => {
				if (closed.code === 1000) send('event: end\ndata: {}\n\n');
				else if (closed.code === UNKNOWN_MATCH) send('event: missing\ndata: {}\n\n');
				finish();
			};
			socket.onerror = () => {
				// A close follows every error; the close ends the response.
			};
		},
		cancel() {
			open = false;
			socket?.close();
		}
	});
}
